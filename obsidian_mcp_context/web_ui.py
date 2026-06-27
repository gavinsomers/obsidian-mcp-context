from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import (
    agent_context,
    build_warehouse,
    entity_timeline,
    list_entities,
    warehouse_summary,
)


DEFAULT_LIMIT = 25


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
    for entity in entities:
        name = str(entity["name"])
        if name.casefold() in lowered:
            return name
    return None


def answer_question(vault_path: Path, question: str) -> dict[str, object]:
    warehouse = _load_warehouse(vault_path)
    summary = warehouse_summary(warehouse)
    entities = list_entities(warehouse, limit=500)
    entity = _extract_entity(question, entities)
    lowered = question.casefold()

    if "summary" in lowered or "counts" in lowered:
        return {"mode": "summary", "summary": summary}
    if "entities" in lowered or "people" in lowered or "companies" in lowered:
        return {"mode": "entities", "results": entities[:DEFAULT_LIMIT]}
    if entity and ("timeline" in lowered or "interactions" in lowered):
        return {
            "mode": "timeline",
            "entity": entity,
            "results": entity_timeline(warehouse, entity=entity, limit=DEFAULT_LIMIT),
        }
    return {
        "mode": "context",
        "entity": entity,
        "results": agent_context(
            warehouse,
            text=question if not entity else None,
            entity=entity,
            limit=DEFAULT_LIMIT,
        ),
    }


def _render_rows(rows: list[dict[str, object]]) -> str:
    if not rows:
        return '<p class="empty">No rows.</p>'
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
    return "\n".join(rendered)


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


def _page(vault_path: Path, values: dict[str, list[str]]) -> str:
    question = _first(values, "q") or "timeline interactions with Marcus Vance"
    answer = answer_question(vault_path, question)
    if answer["mode"] == "summary":
        content = _render_summary(answer["summary"])
    else:
        content = _render_rows(answer["results"])
    escaped_question = escape(question, quote=True)
    escaped_mode = escape(str(answer["mode"]))
    escaped_entity = escape(str(answer.get("entity") or ""))
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
      <span class="pill">entity: {escaped_entity or "none"}</span>
      <span class="pill">vault: {escape(str(vault_path))}</span>
    </div>
    {content}
  </main>
</body>
</html>
"""


class ContextHandler(BaseHTTPRequestHandler):
    vault_path: Path

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        values = parse_qs(parsed.query)
        warehouse = None
        if parsed.path == "/":
            _html_response(self, _page(self.vault_path, values))
            return
        if parsed.path == "/api/ask":
            question = _first(values, "q") or ""
            _json_response(self, answer_question(self.vault_path, question))
            return
        if parsed.path == "/api/summary":
            warehouse = _load_warehouse(self.vault_path)
            _json_response(self, warehouse_summary(warehouse))
            return
        if parsed.path == "/api/entities":
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
        _not_found(self)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-web",
        description="Run a small web UI over the deterministic Obsidian warehouse.",
    )
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = type(
        "ConfiguredContextHandler",
        (ContextHandler,),
        {"vault_path": Path(args.vault).expanduser().resolve()},
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
