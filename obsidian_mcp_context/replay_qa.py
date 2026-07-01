from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from obsidian_mcp_context.ai import (
    AIProvider,
    AIProviderError,
    ContextOverflowError,
    OllamaProvider,
)
from obsidian_mcp_context.config import load_app_config
from obsidian_mcp_context.replay_dashboard import dashboard_status
from obsidian_mcp_context.services import ContextService, default_context_service


MAX_QUESTION_LENGTH = 500
MAX_LIMIT = 50
SUMMARY_PROMPT_VERSION = "replay-qa-summary-v1"
DEFAULT_SUMMARY_MODEL = "gemma4:26b-a4b-it-q4_K_M"
DEFAULT_SUMMARY_CONTEXT_CHARS = 12000
SUMMARY_ROW_LIMIT = 12
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["answer", "citations"],
}

QUESTION_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
DECISION_WORDS = {"decision", "decisions", "decided"}
RISK_WORDS = {"risk", "risks", "blocker", "blockers"}
OPEN_LOOP_WORDS = {"open", "loop", "loops", "todo", "task", "tasks", "followup", "follow-up"}
TIMELINE_WORDS = {"timeline", "history", "when", "sequence"}


def answer_question(
    question: str,
    *,
    vault_path: str | Path,
    state_dir: Path,
    postgres_dsn: str | None = None,
    raw_schema: str = "raw",
    mart_schema: str = "marts",
    service: ContextService = default_context_service,
    limit: int = 12,
    summarize: bool = False,
    summarizer: AIProvider | None = None,
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    summary_base_url: str | None = None,
    summary_max_context_chars: int = DEFAULT_SUMMARY_CONTEXT_CHARS,
) -> dict[str, object]:
    cleaned = question.strip()
    if not cleaned:
        return _error_answer("empty_question", "Ask a question about the replayed vault.")
    if len(cleaned) > MAX_QUESTION_LENGTH:
        return _error_answer(
            "question_too_long",
            f"Question is too long. Keep it under {MAX_QUESTION_LENGTH} characters.",
        )

    freshness = dashboard_status(
        state_dir=state_dir,
        postgres_dsn=postgres_dsn,
        raw_schema=raw_schema,
        mart_schema=mart_schema,
    )
    if not service.dbt_reader(postgres_dsn):
        return _fallback_answer(
            cleaned,
            vault_path=vault_path,
            freshness=freshness,
            service=service,
            limit=limit,
        )

    entity = _resolve_entity(cleaned, vault_path=vault_path, service=service, postgres_dsn=postgres_dsn)
    question_types = _question_types(cleaned)
    rows = _mart_rows(
        cleaned,
        entity=entity,
        question_types=question_types,
        vault_path=vault_path,
        postgres_dsn=postgres_dsn,
        service=service,
        limit=limit,
    )
    if not rows:
        target = entity["name"] if entity else cleaned
        return {
            "status": "no_match",
            "mode": "mart-backed",
            "question": cleaned,
            "answer": f"No mart-backed context matched {target!r}.",
            "deterministic_answer": f"No mart-backed context matched {target!r}.",
            "entity": entity,
            "rows": [],
            "sources": [],
            "summary": {
                "enabled": bool(summarize),
                "status": "no_evidence" if summarize else "not_requested",
                "reason": "No retrieved evidence was available to summarize.",
            },
            "freshness": freshness,
            "generated_at": _now(),
        }

    deterministic_answer = _compose_answer(cleaned, rows, entity=entity)
    payload = {
        "status": "ok",
        "mode": "mart-backed",
        "question": cleaned,
        "answer": deterministic_answer,
        "deterministic_answer": deterministic_answer,
        "entity": entity,
        "question_types": sorted(question_types),
        "rows": rows,
        "sources": _sources(rows),
        "freshness": freshness,
        "generated_at": _now(),
    }
    if summarize:
        _apply_summary(
            payload,
            question=cleaned,
            rows=rows,
            sources=payload["sources"],
            summarizer=summarizer,
            model=summary_model,
            base_url=summary_base_url,
            max_context_chars=summary_max_context_chars,
        )
    else:
        payload["summary"] = {"enabled": False, "status": "not_requested"}
    return payload


def serve_qa(
    *,
    host: str,
    port: int,
    vault_path: str | Path,
    state_dir: Path,
    postgres_dsn: str | None,
    raw_schema: str,
    mart_schema: str,
    summary_model: str,
    summary_base_url: str | None,
    summary_max_context_chars: int,
    service: ContextService = default_context_service,
) -> None:
    handler = _handler(
        vault_path=vault_path,
        state_dir=state_dir,
        postgres_dsn=postgres_dsn,
        raw_schema=raw_schema,
        mart_schema=mart_schema,
        service=service,
        summary_model=summary_model,
        summary_base_url=summary_base_url,
        summary_max_context_chars=summary_max_context_chars,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Replay Q&A listening on http://{host}:{port}")
    server.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-replay-qa",
        description="Serve a local browser Q&A page for mart-backed replay context.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8084)
    parser.add_argument(
        "--vault",
        default=os.environ.get("VAULT_PATH", "var/replay-vault"),
        help="Replay target vault mounted for parser diagnostic fallback.",
    )
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("REPLAY_STATE_DIR", "var/replay-vault"),
        help="Replay target vault containing replay and scheduler state files.",
    )
    parser.add_argument("--postgres-dsn", default=os.environ.get("POSTGRES_DSN"))
    parser.add_argument("--raw-schema", default=os.environ.get("POSTGRES_RAW_SCHEMA", "raw"))
    parser.add_argument("--mart-schema", default=os.environ.get("DBT_TARGET_SCHEMA", "marts"))
    parser.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path for parser diagnostic settings.",
    )
    parser.add_argument(
        "--vault-profile",
        help=(
            "Optional vault profile TOML path or checked-in profile name from "
            "examples/vault-profiles. Loaded before --config."
        ),
    )
    parser.add_argument(
        "--summary-model",
        default=os.environ.get("REPLAY_QA_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL),
        help="Local Ollama model for optional answer composition.",
    )
    parser.add_argument(
        "--summary-base-url",
        default=os.environ.get("REPLAY_QA_OLLAMA_BASE_URL")
        or os.environ.get("OLLAMA_BASE_URL"),
        help="Ollama base URL for optional answer composition.",
    )
    parser.add_argument(
        "--summary-max-context-chars",
        type=int,
        default=int(
            os.environ.get(
                "REPLAY_QA_SUMMARY_MAX_CONTEXT_CHARS",
                str(DEFAULT_SUMMARY_CONTEXT_CHARS),
            )
        ),
        help="Maximum prompt size for local answer composition.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = default_context_service
    if args.config or args.vault_profile or os.environ.get("OBSIDIAN_MCP_VAULT_PROFILE"):
        service = ContextService(
            app_config=load_app_config(
                args.config,
                profile_path=args.vault_profile,
            )
        )
    serve_qa(
        host=args.host,
        port=args.port,
        vault_path=args.vault,
        state_dir=Path(args.state_dir),
        postgres_dsn=args.postgres_dsn,
        raw_schema=args.raw_schema,
        mart_schema=args.mart_schema,
        service=service,
        summary_model=args.summary_model,
        summary_base_url=args.summary_base_url,
        summary_max_context_chars=args.summary_max_context_chars,
    )
    return 0


def _handler(
    *,
    vault_path: str | Path,
    state_dir: Path,
    postgres_dsn: str | None,
    raw_schema: str,
    mart_schema: str,
    service: ContextService = default_context_service,
    summarizer: AIProvider | None = None,
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    summary_base_url: str | None = None,
    summary_max_context_chars: int = DEFAULT_SUMMARY_CONTEXT_CHARS,
) -> type[BaseHTTPRequestHandler]:
    class ReplayQaHandler(BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/api/status"}:
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8"
                    if path == "/"
                    else "application/json; charset=utf-8",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._send_text(HTTPStatus.OK, _HTML, content_type="text/html; charset=utf-8")
                return
            if path == "/api/status":
                self._send_json(
                    HTTPStatus.OK,
                    dashboard_status(
                        state_dir=state_dir,
                        postgres_dsn=postgres_dsn,
                        raw_schema=raw_schema,
                        mart_schema=mart_schema,
                    ),
                )
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/api/ask":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                question = str(payload.get("question", ""))
                summarize = bool(payload.get("summarize", False))
                answer = answer_question(
                    question,
                    vault_path=vault_path,
                    state_dir=state_dir,
                    postgres_dsn=postgres_dsn,
                    raw_schema=raw_schema,
                    mart_schema=mart_schema,
                    service=service,
                    summarize=summarize,
                    summarizer=summarizer,
                    summary_model=summary_model,
                    summary_base_url=summary_base_url,
                    summary_max_context_chars=summary_max_context_chars,
                )
            except json.JSONDecodeError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                return
            except Exception as exc:  # pragma: no cover - HTTP boundary safety.
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, answer)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(
            self,
            status: HTTPStatus,
            body: str,
            *,
            content_type: str,
        ) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return ReplayQaHandler


def _resolve_entity(
    question: str,
    *,
    vault_path: str | Path,
    service: ContextService,
    postgres_dsn: str | None,
) -> dict[str, object] | None:
    entities = _matching_entities(
        question,
        service.list_entities(
            vault_path,
            text=None,
            limit=500,
            postgres_dsn=postgres_dsn,
        ),
    )
    if not entities:
        for term in _candidate_entity_terms(question):
            entities = _matching_entities(
                question,
                service.list_entities(
                    vault_path,
                    text=term,
                    limit=50,
                    postgres_dsn=postgres_dsn,
                ),
            )
            if entities:
                break
    if not entities:
        return None
    return max(entities, key=_entity_match_score)


def _matching_entities(
    question: str,
    entities: list[dict[str, object]],
) -> list[dict[str, object]]:
    folded_question = question.casefold()
    return [
        entity
        for entity in entities
        if str(entity.get("name", "")).casefold() in folded_question
    ]


def _candidate_entity_terms(question: str) -> list[str]:
    words = [match.group(0) for match in QUESTION_WORD_RE.finditer(question)]
    terms: list[str] = []
    seen: set[str] = set()
    for width in range(min(5, len(words)), 1, -1):
        for index in range(0, len(words) - width + 1):
            term = " ".join(words[index : index + width])
            folded = term.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            terms.append(term)
    return terms


def _entity_match_score(entity: dict[str, object]) -> tuple[int, int]:
    entity_type = str(entity.get("entity_type") or "")
    type_score = {
        "project": 4,
        "person": 3,
        "company": 2,
    }.get(entity_type, 1)
    return (type_score, len(str(entity.get("name", ""))))


def _question_types(question: str) -> set[str]:
    words = {match.group(0).casefold() for match in QUESTION_WORD_RE.finditer(question)}
    types: set[str] = set()
    if words & DECISION_WORDS:
        types.add("decisions")
    if words & RISK_WORDS:
        types.add("risks")
    if words & OPEN_LOOP_WORDS:
        types.add("open_loops")
    if words & TIMELINE_WORDS:
        types.add("timeline")
    return types or {"context"}


def _mart_rows(
    question: str,
    *,
    entity: dict[str, object] | None,
    question_types: set[str],
    vault_path: str | Path,
    postgres_dsn: str | None,
    service: ContextService,
    limit: int,
) -> list[dict[str, object]]:
    bounded_limit = max(1, min(limit, MAX_LIMIT))
    if entity:
        entity_name = str(entity["name"])
        entity_type = str(entity["entity_type"])
        rows: list[dict[str, object]] = []
        if "decisions" in question_types:
            rows.extend(service.decisions(postgres_dsn, entity=entity_name, limit=bounded_limit))
        if "risks" in question_types:
            rows.extend(service.risks(postgres_dsn, entity=entity_name, limit=bounded_limit))
        if "open_loops" in question_types:
            rows.extend(service.open_loops(postgres_dsn, entity=entity_name, limit=bounded_limit))
        if "timeline" in question_types or "context" in question_types or not rows:
            if entity_type == "project":
                rows.extend(service.project_context(postgres_dsn, project=entity_name, limit=bounded_limit))
            elif entity_type == "person":
                rows.extend(service.person_context(postgres_dsn, person=entity_name, limit=bounded_limit))
            else:
                rows.extend(
                    service.entity_context_generic(
                        postgres_dsn,
                        entity_type=entity_type,
                        entity=entity_name,
                        limit=bounded_limit,
                    )
                )
        return _dedupe_rows(rows)[:bounded_limit]

    words = " ".join(match.group(0) for match in QUESTION_WORD_RE.finditer(question))
    rows = service.agent_context(
        vault_path,
        text=words or None,
        limit=bounded_limit,
        postgres_dsn=postgres_dsn,
    )
    return _dedupe_rows(rows)[:bounded_limit]


def _fallback_answer(
    question: str,
    *,
    vault_path: str | Path,
    freshness: dict[str, object],
    service: ContextService,
    limit: int,
) -> dict[str, object]:
    rows = service.search_blocks(vault_path, text=question, limit=min(limit, 10))
    return {
        "status": "fallback" if rows else "warehouse_unavailable",
        "mode": "parser-diagnostic-fallback" if rows else "unavailable",
        "question": question,
        "answer": (
            "No valid dbt warehouse is available. Showing parser diagnostic matches."
            if rows
            else "No valid dbt warehouse is available and parser diagnostics found no matches."
        ),
        "deterministic_answer": (
            "No valid dbt warehouse is available. Showing parser diagnostic matches."
            if rows
            else "No valid dbt warehouse is available and parser diagnostics found no matches."
        ),
        "entity": None,
        "rows": rows,
        "sources": _sources(rows),
        "summary": {
            "enabled": False,
            "status": "not_available",
            "reason": "Summarization only runs after mart-backed retrieval returns evidence.",
        },
        "freshness": freshness,
        "generated_at": _now(),
    }


def _dedupe_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[object, object, object, object]] = set()
    deduped: list[dict[str, object]] = []
    for row in rows:
        key = (
            row.get("row_id"),
            row.get("source_path"),
            row.get("start_line"),
            row.get("summary"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _compose_answer(
    question: str,
    rows: list[dict[str, object]],
    *,
    entity: dict[str, object] | None,
) -> str:
    target = str(entity["name"]) if entity else "the current vault"
    facts = []
    for row in rows[:6]:
        event_type = str(row.get("event_type") or "context").replace("_", " ")
        title = str(row.get("title") or row.get("source_path") or "Untitled")
        summary = str(row.get("summary") or "").strip()
        if summary:
            facts.append(f"{event_type}: {title} - {summary}")
        else:
            facts.append(f"{event_type}: {title}")
    return (
        f"Mart-backed context for {target} matched the question {question!r}. "
        + " ".join(facts)
    )


def _apply_summary(
    payload: dict[str, object],
    *,
    question: str,
    rows: list[dict[str, object]],
    sources: object,
    summarizer: AIProvider | None,
    model: str,
    base_url: str | None,
    max_context_chars: int,
) -> None:
    try:
        provider = summarizer or OllamaProvider(
            model=model,
            base_url=base_url or "http://localhost:11434",
        )
        prompt = _summary_prompt(question, rows, sources)
        result = provider.complete_json(
            prompt,
            SUMMARY_SCHEMA,
            max_context_chars=max_context_chars,
            prompt_version=SUMMARY_PROMPT_VERSION,
        )
        answer = str(result.data.get("answer", "")).strip()
        if not answer:
            raise AIProviderError("summary response did not include a non-empty answer")
    except ContextOverflowError as exc:
        payload["summary"] = {
            "enabled": True,
            "status": "context_overflow",
            "provider": getattr(summarizer, "provider", "ollama"),
            "model": getattr(summarizer, "model", model),
            "error": str(exc),
        }
        return
    except AIProviderError as exc:
        payload["summary"] = {
            "enabled": True,
            "status": "provider_error",
            "provider": getattr(summarizer, "provider", "ollama"),
            "model": getattr(summarizer, "model", model),
            "error": str(exc),
        }
        return

    payload["answer"] = answer
    payload["mode"] = "mart-backed+local-gemma"
    payload["summary"] = {
        "enabled": True,
        "status": "ok",
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "input_hash": result.input_hash,
        "created_at": result.created_at,
        "citations": result.data.get("citations", []),
    }


def _summary_prompt(
    question: str,
    rows: list[dict[str, object]],
    sources: object,
) -> str:
    evidence = []
    for index, row in enumerate(rows[:SUMMARY_ROW_LIMIT], start=1):
        evidence.append(
            {
                "citation": index,
                "event_date": row.get("event_date") or row.get("source_date"),
                "event_type": row.get("event_type"),
                "title": row.get("title"),
                "summary": row.get("summary") or row.get("text") or row.get("task_text"),
                "source_path": row.get("source_path"),
                "start_line": row.get("start_line") or row.get("line_number"),
            }
        )
    return "\n".join(
        [
            "You summarize deterministic dbt/MCP retrieval results for a local demo.",
            "Use only the evidence rows provided. Do not invent facts or sources.",
            "If evidence is thin, say so briefly.",
            "Cite evidence using bracketed numbers like [1].",
            "Return JSON matching the requested schema.",
            "",
            f"Question: {question}",
            "",
            "Evidence rows:",
            json.dumps(evidence, indent=2, sort_keys=True),
            "",
            "Available source records:",
            json.dumps(sources, indent=2, sort_keys=True),
        ]
    )


def _sources(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, object]] = set()
    sources: list[dict[str, object]] = []
    for row in rows:
        source_path = row.get("source_path")
        if not source_path:
            continue
        key = (str(source_path), row.get("start_line"))
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "source_path": source_path,
                "start_line": row.get("start_line"),
                "title": row.get("title"),
                "event_type": row.get("event_type"),
            }
        )
    return sources


def _error_answer(code: str, message: str) -> dict[str, object]:
    return {
        "status": "error",
        "mode": "unavailable",
        "error": code,
        "answer": message,
        "rows": [],
        "sources": [],
        "generated_at": _now(),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Replay Q&A</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-2: #eef1f4;
      --text: #18202c;
      --muted: #637083;
      --line: #d7dee8;
      --accent: #0b6bcb;
      --ok: #087443;
      --warn: #8a5a00;
      --bad: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
    h2 { margin: 0 0 10px; font-size: 15px; letter-spacing: 0; }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px;
      display: grid;
      gap: 16px;
    }
    .status {
      display: inline-flex;
      min-height: 28px;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-weight: 700;
      color: var(--muted);
      background: var(--panel-2);
    }
    .status.ok { color: var(--ok); background: #e8f5ee; }
    .status.warn { color: var(--warn); background: #fff3d6; }
    .status.bad { color: var(--bad); background: #fdeceb; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: start;
    }
    .ask-controls {
      display: grid;
      gap: 10px;
      align-content: start;
    }
    .toggle {
      min-height: 32px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
      white-space: nowrap;
    }
    .toggle input {
      width: 16px;
      height: 16px;
      margin: 0;
      accent-color: var(--accent);
    }
    textarea {
      width: 100%;
      min-height: 78px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      color: var(--text);
      font: inherit;
      background: #fff;
    }
    button {
      min-height: 40px;
      border: 1px solid #0959a8;
      border-radius: 6px;
      padding: 0 14px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    .meta {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      background: var(--panel-2);
      border-radius: 6px;
      padding: 10px;
      min-height: 74px;
    }
    .label { color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; }
    .value { margin-top: 4px; font-size: 18px; font-weight: 750; overflow-wrap: anywhere; }
    .subtle { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
    .answer {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 15px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 8px 6px;
      vertical-align: top;
    }
    th { color: var(--muted); font-size: 12px; }
    code {
      background: var(--panel-2);
      border-radius: 4px;
      padding: 1px 4px;
      overflow-wrap: anywhere;
    }
    @media (max-width: 840px) {
      header, main { padding: 16px; }
      form, .meta { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Replay Q&A</h1>
      <div class="subtle">Ask against current generated-vault mart context</div>
    </div>
    <div id="ready" class="status">Loading</div>
  </header>
  <main>
    <section class="panel">
      <form id="askForm">
        <textarea id="question" maxlength="500">What are the risks and open loops for Project Atlas 1?</textarea>
        <div class="ask-controls">
          <button id="askButton" type="submit">Ask</button>
          <label class="toggle"><input id="summarize" type="checkbox"> Local Gemma</label>
        </div>
      </form>
    </section>

    <section class="meta">
      <div class="metric"><div class="label">Mode</div><div id="mode" class="value">-</div></div>
      <div class="metric"><div class="label">Entity</div><div id="entity" class="value">-</div></div>
      <div class="metric"><div class="label">Virtual Time</div><div id="virtualTime" class="value">-</div></div>
      <div class="metric"><div class="label">Summary</div><div id="summaryStatus" class="value">-</div><div id="summaryModel" class="subtle">-</div></div>
    </section>

    <section class="panel">
      <h2>Answer</h2>
      <div id="answer" class="answer">Waiting for a question.</div>
    </section>

    <section class="panel">
      <h2>Sources</h2>
      <table><thead><tr><th>Source</th><th>Line</th><th>Type</th><th>Title</th></tr></thead><tbody id="sources"></tbody></table>
    </section>

    <section class="panel">
      <h2>Matched Rows</h2>
      <table><thead><tr><th>Date</th><th>Type</th><th>Summary</th><th>Source</th></tr></thead><tbody id="rows"></tbody></table>
    </section>
  </main>
  <script>
    const fmt = value => value === null || value === undefined || value === "" ? "-" : String(value);
    const escapeHtml = value => fmt(value).replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
    function setReady(status) {
      const el = document.getElementById("ready");
      const ready = status && status.readiness && status.readiness.ready;
      el.className = ready ? "status ok" : "status warn";
      el.textContent = ready ? "Ready" : "Not ready";
    }
    function renderAnswer(data) {
      const freshness = data.freshness || {};
      const replay = freshness.replay || {};
      const entity = data.entity || {};
      const summary = data.summary || {};
      document.getElementById("mode").textContent = fmt(data.mode);
      document.getElementById("entity").textContent = fmt(entity.name);
      document.getElementById("virtualTime").textContent = fmt(replay.virtual_time);
      document.getElementById("summaryStatus").textContent = summary.enabled ? fmt(summary.status) : "off";
      document.getElementById("summaryModel").textContent = summary.model ? fmt(summary.model) : `${fmt((data.rows || []).length)} rows`;
      document.getElementById("answer").textContent = fmt(data.answer);
      document.getElementById("sources").innerHTML = (data.sources || []).map(source =>
        `<tr><td><code>${escapeHtml(source.source_path)}</code></td><td>${escapeHtml(source.start_line)}</td><td>${escapeHtml(source.event_type)}</td><td>${escapeHtml(source.title)}</td></tr>`
      ).join("") || "<tr><td colspan='4'>No sources returned</td></tr>";
      document.getElementById("rows").innerHTML = (data.rows || []).map(row =>
        `<tr><td>${escapeHtml(row.event_date || row.source_date)}</td><td>${escapeHtml(row.event_type)}</td><td>${escapeHtml(row.summary || row.text || row.task_text)}</td><td><code>${escapeHtml(row.source_path)}</code></td></tr>`
      ).join("") || "<tr><td colspan='4'>No rows returned</td></tr>";
      setReady(freshness);
    }
    async function refreshStatus() {
      const response = await fetch("/api/status", { cache: "no-store" });
      setReady(await response.json());
    }
    document.getElementById("askForm").addEventListener("submit", async event => {
      event.preventDefault();
      const button = document.getElementById("askButton");
      button.disabled = true;
      try {
        const response = await fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: document.getElementById("question").value,
            summarize: document.getElementById("summarize").checked
          })
        });
        renderAnswer(await response.json());
      } catch (error) {
        document.getElementById("ready").className = "status bad";
        document.getElementById("ready").textContent = "Error";
        document.getElementById("answer").textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
    refreshStatus().catch(() => {});
    setInterval(refreshStatus, 5000);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
