from __future__ import annotations

import argparse
import os
from html import escape
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from obsidian_mcp_context import dbt_warehouse
from obsidian_mcp_context.status import warehouse_status
from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import (
    agent_context,
    build_warehouse,
    entity_timeline,
    list_entities,
    warehouse_summary,
)


DEFAULT_LIMIT = 25
ENTITY_QUERY_TYPES = {
    "people": "person",
    "person": "person",
    "companies": "company",
    "company": "company",
    "projects": "project",
    "project": "project",
}


def _load_warehouse(vault_path: Path):
    context = build_context(VaultConfig(vault_path=vault_path))
    return build_warehouse(context)


def _first(values: dict[str, list[str]], key: str) -> str | None:
    value = values.get(key, [""])[0].strip()
    return value or None


def _json_response(handler: BaseHTTPRequestHandler, value: object) -> None:
    payload = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _html_response(handler: BaseHTTPRequestHandler, body: str) -> None:
    payload = body.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _not_found(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(404)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(b"Not found")


def _extract_entity(question: str, entities: list[dict[str, object]]) -> str | None:
    lowered = question.casefold()
    for entity in sorted(entities, key=lambda row: len(str(row["name"])), reverse=True):
        name = str(entity["name"])
        if name.casefold() in lowered:
            return name
    return None


def _requested_entity_types(question: str) -> list[str]:
    lowered_words = set(question.casefold().replace(",", " ").split())
    requested = []
    for word, entity_type in ENTITY_QUERY_TYPES.items():
        if word in lowered_words and entity_type not in requested:
            requested.append(entity_type)
    return requested


def _dbt_answer_question(
    duckdb_path: Path,
    question: str,
) -> dict[str, object] | None:
    entities = dbt_warehouse.list_entities(duckdb_path, limit=500)
    entity = _extract_entity(question, entities)
    entity_row = next(
        (row for row in entities if entity and str(row["name"]) == entity),
        None,
    )
    lowered = question.casefold()
    wants_timeline = "timeline" in lowered or "interactions" in lowered
    wants_open_loops = "open loop" in lowered or "open task" in lowered
    wants_decisions = "decision" in lowered
    wants_risks = "risk" in lowered
    requested_types = _requested_entity_types(question)

    if "summary" in lowered or "counts" in lowered:
        return {
            "mode": "summary",
            "warehouse": "dbt",
            "summary": dbt_warehouse.summary(duckdb_path),
        }
    if requested_types and not entity:
        groups = [
            {
                "entity_type": entity_type,
                "results": dbt_warehouse.list_entities(
                    duckdb_path,
                    entity_type=entity_type,
                    limit=DEFAULT_LIMIT,
                ),
            }
            for entity_type in requested_types
        ]
        return {"mode": "entity_groups", "warehouse": "dbt", "groups": groups}
    if "entities" in lowered:
        return {
            "mode": "entities",
            "warehouse": "dbt",
            "results": entities[:DEFAULT_LIMIT],
        }
    if entity_row and str(entity_row["entity_type"]) == "project":
        return {
            "mode": "project_context",
            "warehouse": "dbt",
            "entity": entity,
            "results": dbt_warehouse.project_context(
                duckdb_path,
                project=entity,
                limit=DEFAULT_LIMIT,
            ),
        }
    if entity_row and str(entity_row["entity_type"]) == "person":
        return {
            "mode": "person_context",
            "warehouse": "dbt",
            "entity": entity,
            "results": dbt_warehouse.person_context(
                duckdb_path,
                person=entity,
                limit=DEFAULT_LIMIT,
            ),
        }
    if wants_open_loops:
        return {
            "mode": "open_loops",
            "warehouse": "dbt",
            "entity": entity,
            "results": dbt_warehouse.list_open_loops(
                duckdb_path,
                entity=entity,
                limit=DEFAULT_LIMIT,
            ),
        }
    if wants_decisions and not wants_timeline:
        return {
            "mode": "decisions",
            "warehouse": "dbt",
            "entity": entity,
            "results": dbt_warehouse.list_decisions(
                duckdb_path,
                entity=entity,
                limit=DEFAULT_LIMIT,
            ),
        }
    if wants_risks and not wants_timeline:
        return {
            "mode": "risks",
            "warehouse": "dbt",
            "entity": entity,
            "results": dbt_warehouse.list_risks(
                duckdb_path,
                entity=entity,
                limit=DEFAULT_LIMIT,
            ),
        }
    if wants_timeline:
        return {
            "mode": "entity_lookup",
            "warehouse": "dbt",
            "entity": None,
            "message": (
                "No matching entity was found in this warehouse. Try one of the "
                "known people, companies, projects, decisions, risks, or topics below."
            ),
            "results": entities[:DEFAULT_LIMIT],
        }
    return None


def answer_question(
    vault_path: Path,
    question: str,
    duckdb_path: Path | None = None,
) -> dict[str, object]:
    resolved_duckdb_path = dbt_warehouse.resolve_duckdb_path(
        duckdb_path or os.environ.get("DUCKDB_PATH")
    )
    if resolved_duckdb_path and dbt_warehouse.is_available(resolved_duckdb_path):
        dbt_answer = _dbt_answer_question(resolved_duckdb_path, question)
        if dbt_answer is not None:
            return dbt_answer

    warehouse = _load_warehouse(vault_path)
    summary = warehouse_summary(warehouse)
    entities = list_entities(warehouse, limit=500)
    entity = _extract_entity(question, entities)
    lowered = question.casefold()
    wants_timeline = "timeline" in lowered or "interactions" in lowered
    requested_types = _requested_entity_types(question)

    if "summary" in lowered or "counts" in lowered:
        return {"mode": "summary", "warehouse": "memory", "summary": summary}
    if entity and wants_timeline:
        return {
            "mode": "timeline",
            "warehouse": "memory",
            "entity": entity,
            "results": entity_timeline(warehouse, entity=entity, limit=DEFAULT_LIMIT),
        }
    if wants_timeline:
        return {
            "mode": "entity_lookup",
            "warehouse": "memory",
            "entity": None,
            "message": (
                "No matching entity was found in this vault. Try one of the known "
                "people, companies, projects, decisions, risks, or topics below."
            ),
            "results": entities[:DEFAULT_LIMIT],
        }
    if requested_types and not entity:
        groups = [
            {
                "entity_type": entity_type,
                "results": [
                    row
                    for row in entities
                    if str(row.get("entity_type")) == entity_type
                ][:DEFAULT_LIMIT],
            }
            for entity_type in requested_types
        ]
        return {"mode": "entity_groups", "warehouse": "memory", "groups": groups}
    if "entities" in lowered:
        return {
            "mode": "entities",
            "warehouse": "memory",
            "results": entities[:DEFAULT_LIMIT],
        }
    return {
        "mode": "context",
        "warehouse": "memory",
        "entity": entity,
        "results": agent_context(
            warehouse,
            text=question if not entity else None,
            entity=entity,
            limit=DEFAULT_LIMIT,
        ),
    }


def _render_rows(rows: list[dict[str, object]], message: str | None = None) -> str:
    rendered_message = ""
    if message:
        rendered_message = f'<p class="notice">{escape(message)}</p>'
    if not rows:
        return rendered_message + '<p class="empty">No rows matched this query.</p>'
    rendered = []
    for row in rows:
        title = escape(str(row.get("title") or row.get("name") or row.get("source_path")))
        source = escape(str(row.get("source_path") or row.get("entity_type") or ""))
        summary = escape(str(row.get("summary") or row.get("entity_id") or ""))
        date = escape(str(row.get("event_date") or ""))
        lines = ""
        if row.get("start_line"):
            lines = f":{escape(str(row['start_line']))}"
        rendered.append(
            f"""
            <article class="row">
              <header>
                <strong>{title}</strong>
                <span>{date}</span>
              </header>
              <div class="source">{source}{lines}</div>
              <pre>{summary}</pre>
            </article>
            """
        )
    return rendered_message + "\n".join(rendered)


def _render_summary(summary: dict[str, object]) -> str:
    tables = summary["tables"]
    entities = summary["entity_types"]
    table_rows = "\n".join(
        f"<tr><td>{escape(str(name))}</td><td>{count}</td></tr>"
        for name, count in tables.items()
    )
    entity_rows = "\n".join(
        f"<tr><td>{escape(str(row['entity_type']))}</td><td>{row['count']}</td></tr>"
        for row in entities
    )
    return f"""
    <section class="grid">
      <table><thead><tr><th>Table</th><th>Rows</th></tr></thead><tbody>{table_rows}</tbody></table>
      <table><thead><tr><th>Entity</th><th>Rows</th></tr></thead><tbody>{entity_rows}</tbody></table>
    </section>
    """


def _render_entity_groups(groups: list[dict[str, object]]) -> str:
    sections = []
    for group in groups:
        entity_type = escape(str(group["entity_type"]).title())
        rows = group.get("results", [])
        sections.append(
            f"""
            <section class="group">
              <h2>{entity_type}</h2>
              {_render_rows(rows)}
            </section>
            """
        )
    return "\n".join(sections)


def _render_status_panel(status: dict[str, object]) -> str:
    warehouse = status["warehouse"]
    simulation = status["simulation"]
    active_reader = warehouse["active_reader"]
    writer = warehouse["writer"]
    read_snapshot = warehouse["read_snapshot"]
    row_counts = warehouse["row_counts"]
    simulation_state = simulation.get("state") or {}
    key_tables = (
        "base_obsidian_files",
        "dim_notes",
        "dim_entities",
        "fact_tasks",
        "fact_mentions",
        "mart_open_loops",
        "mart_project_context",
        "mart_person_context",
    )
    count_cells = "\n".join(
        f"""
        <div class="stat">
          <span>{escape(table)}</span>
          <strong>{escape(str(row_counts.get(table) if row_counts.get(table) is not None else "n/a"))}</strong>
        </div>
        """
        for table in key_tables
    )
    virtual_date = simulation_state.get("virtual_date") or "n/a"
    run_number = simulation_state.get("run_number")
    run_label = f"run {run_number}" if run_number is not None else "run n/a"
    read_label = "yes" if warehouse["reading_from_stable_snapshot"] else "no"
    writer_label = "present" if writer["exists"] else "missing"
    read_snapshot_label = "present" if read_snapshot["exists"] else "missing"
    active_label = "available" if active_reader["available"] else "unavailable"
    return f"""
    <section class="status-panel" aria-label="Pipeline status">
      <div class="status-head">
        <div>
          <h2>Pipeline Status</h2>
          <p>Virtual date {escape(str(virtual_date))} · {escape(run_label)}</p>
        </div>
        <div class="status-badges">
          <span class="pill">reader: {escape(active_label)}</span>
          <span class="pill">stable snapshot: {escape(read_label)}</span>
        </div>
      </div>
      <div class="status-grid">
        <div class="stat">
          <span>writer warehouse</span>
          <strong>{escape(writer_label)}</strong>
        </div>
        <div class="stat">
          <span>read snapshot</span>
          <strong>{escape(read_snapshot_label)}</strong>
        </div>
        {count_cells}
      </div>
    </section>
    """


def _page(vault_path: Path, duckdb_path: Path | None, values: dict[str, list[str]]) -> str:
    question = _first(values, "q") or "summary counts"
    answer = answer_question(vault_path, question, duckdb_path=duckdb_path)
    status = warehouse_status(vault_path, active_duckdb_path=duckdb_path)
    if answer["mode"] == "summary":
        content = _render_summary(answer["summary"])
    elif answer["mode"] == "entity_groups":
        content = _render_entity_groups(answer["groups"])
    else:
        content = _render_rows(
            answer["results"],
            message=str(answer.get("message") or "") or None,
        )
    escaped_question = escape(question, quote=True)
    escaped_mode = escape(str(answer["mode"]))
    escaped_entity = escape(str(answer.get("entity") or ""))
    escaped_warehouse = escape(str(answer.get("warehouse") or "memory"))
    status_panel = _render_status_panel(status)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Obsidian MCP Context</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --line: #d8dde5;
      --text: #1d2430;
      --muted: #5f6b7a;
      --accent: #116a75;
    }}
    body {{
      margin: 0;
      font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header.top {{
      padding: 20px 24px 12px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{
      margin: 0 0 14px;
      font-size: 22px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    form {{
      display: flex;
      gap: 8px;
      max-width: 960px;
    }}
    input {{
      flex: 1;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      background: #fff;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      font: inherit;
      font-weight: 650;
      color: #fff;
      background: var(--accent);
      cursor: pointer;
    }}
    main {{
      padding: 18px 24px 32px;
      max-width: 1120px;
    }}
    .meta {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 14px;
      color: var(--muted);
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 9px;
      background: #fff;
    }}
    .status-panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
      margin-bottom: 16px;
    }}
    .status-head {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    .status-head h2 {{
      margin: 0;
      font-size: 17px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    .status-head p {{
      margin: 3px 0 0;
      color: var(--muted);
    }}
    .status-badges {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 8px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fbfcfd;
      min-width: 0;
    }}
    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .stat strong {{
      display: block;
      margin-top: 2px;
      font-size: 15px;
      overflow-wrap: anywhere;
    }}
    .row {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 13px 14px;
      margin: 10px 0;
    }}
    .row header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
    }}
    .group {{
      margin: 0 0 22px;
    }}
    .group h2 {{
      margin: 0 0 8px;
      font-size: 17px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    .source {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      margin: 10px 0 0;
      font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
    }}
    th {{
      background: #eef2f6;
    }}
    .empty {{
      color: var(--muted);
    }}
    .notice {{
      max-width: 760px;
      margin: 0 0 14px;
      padding: 10px 12px;
      border: 1px solid #bfd5db;
      border-radius: 6px;
      background: #eef8fa;
      color: #224f58;
    }}
    @media (max-width: 640px) {{
      form {{ flex-direction: column; }}
      button {{ width: 100%; }}
      header.top, main {{ padding-left: 14px; padding-right: 14px; }}
    }}
  </style>
</head>
<body>
  <header class="top">
    <h1>Obsidian MCP Context</h1>
    <form method="get" action="/">
      <input name="q" value="{escaped_question}" autocomplete="off">
      <button type="submit">Ask</button>
    </form>
  </header>
  <main>
    <div class="meta">
      <span class="pill">mode: {escaped_mode}</span>
      <span class="pill">warehouse: {escaped_warehouse}</span>
      <span class="pill">entity: {escaped_entity or "none"}</span>
      <span class="pill">vault: {escape(str(vault_path))}</span>
    </div>
    {status_panel}
    {content}
  </main>
</body>
</html>
"""


class ContextHandler(BaseHTTPRequestHandler):
    vault_path: Path
    duckdb_path: Path | None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        values = parse_qs(parsed.query)
        warehouse = None
        if parsed.path == "/":
            _html_response(self, _page(self.vault_path, self.duckdb_path, values))
            return
        if parsed.path == "/api/ask":
            question = _first(values, "q") or ""
            _json_response(
                self,
                answer_question(self.vault_path, question, duckdb_path=self.duckdb_path),
            )
            return
        if parsed.path == "/api/summary":
            if self.duckdb_path and dbt_warehouse.is_available(self.duckdb_path):
                _json_response(self, dbt_warehouse.summary(self.duckdb_path))
                return
            warehouse = _load_warehouse(self.vault_path)
            _json_response(self, warehouse_summary(warehouse))
            return
        if parsed.path == "/api/status":
            _json_response(
                self,
                warehouse_status(self.vault_path, active_duckdb_path=self.duckdb_path),
            )
            return
        if parsed.path == "/api/entities":
            if self.duckdb_path and dbt_warehouse.is_available(self.duckdb_path):
                _json_response(
                    self,
                    {
                        "result": dbt_warehouse.list_entities(
                            self.duckdb_path,
                            entity_type=_first(values, "entity_type"),
                            text=_first(values, "text"),
                            limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                        )
                    },
                )
                return
            warehouse = _load_warehouse(self.vault_path)
            _json_response(
                self,
                {
                    "result": list_entities(
                        warehouse,
                        entity_type=_first(values, "entity_type"),
                        text=_first(values, "text"),
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        if parsed.path == "/api/timeline":
            entity = _first(values, "entity")
            if not entity:
                _json_response(self, {"error": "entity is required"})
                return
            warehouse = _load_warehouse(self.vault_path)
            _json_response(
                self,
                {
                    "result": entity_timeline(
                        warehouse,
                        entity=entity,
                        text=_first(values, "text"),
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        if parsed.path == "/api/context":
            warehouse = _load_warehouse(self.vault_path)
            _json_response(
                self,
                {
                    "result": agent_context(
                        warehouse,
                        text=_first(values, "text"),
                        entity=_first(values, "entity"),
                        event_type=_first(values, "event_type"),
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        if parsed.path == "/api/project-context":
            entity = _first(values, "entity")
            if not entity:
                _json_response(self, {"error": "entity is required"})
                return
            if not self.duckdb_path or not dbt_warehouse.is_available(self.duckdb_path):
                _json_response(self, {"error": "dbt warehouse is not available"})
                return
            _json_response(
                self,
                {
                    "result": dbt_warehouse.project_context(
                        self.duckdb_path,
                        project=entity,
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        if parsed.path == "/api/person-context":
            entity = _first(values, "entity")
            if not entity:
                _json_response(self, {"error": "entity is required"})
                return
            if not self.duckdb_path or not dbt_warehouse.is_available(self.duckdb_path):
                _json_response(self, {"error": "dbt warehouse is not available"})
                return
            _json_response(
                self,
                {
                    "result": dbt_warehouse.person_context(
                        self.duckdb_path,
                        person=entity,
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        if parsed.path == "/api/open-loops":
            if not self.duckdb_path or not dbt_warehouse.is_available(self.duckdb_path):
                _json_response(self, {"error": "dbt warehouse is not available"})
                return
            _json_response(
                self,
                {
                    "result": dbt_warehouse.list_open_loops(
                        self.duckdb_path,
                        entity=_first(values, "entity"),
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        if parsed.path == "/api/decisions":
            if not self.duckdb_path or not dbt_warehouse.is_available(self.duckdb_path):
                _json_response(self, {"error": "dbt warehouse is not available"})
                return
            _json_response(
                self,
                {
                    "result": dbt_warehouse.list_decisions(
                        self.duckdb_path,
                        entity=_first(values, "entity"),
                        status=_first(values, "status"),
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        if parsed.path == "/api/risks":
            if not self.duckdb_path or not dbt_warehouse.is_available(self.duckdb_path):
                _json_response(self, {"error": "dbt warehouse is not available"})
                return
            _json_response(
                self,
                {
                    "result": dbt_warehouse.list_risks(
                        self.duckdb_path,
                        entity=_first(values, "entity"),
                        status=_first(values, "status"),
                        limit=int(_first(values, "limit") or DEFAULT_LIMIT),
                    )
                },
            )
            return
        _not_found(self)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-web",
        description="Run a small web UI over the deterministic Obsidian warehouse.",
    )
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault.")
    parser.add_argument(
        "--duckdb",
        default=None,
        help="Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or /warehouse/obsidian.duckdb when present.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    duckdb_path = dbt_warehouse.resolve_duckdb_path(
        args.duckdb or os.environ.get("DUCKDB_PATH")
    )
    handler = type(
        "ConfiguredContextHandler",
        (ContextHandler,),
        {
            "vault_path": Path(args.vault).expanduser().resolve(),
            "duckdb_path": duckdb_path,
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving Obsidian MCP Context UI on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
