from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from urllib.parse import urlparse


REPLAY_STATE_FILE = ".obsidian-mcp-replay-state.json"
SCHEDULER_STATE_FILE = ".obsidian-mcp-scheduler-state.json"
SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

RAW_TABLES = (
    "base_obsidian_files",
    "base_obsidian_blocks",
    "base_obsidian_tasks",
    "base_obsidian_links",
    "base_obsidian_tags",
    "base_obsidian_lines",
)
MART_TABLES = (
    "dim_entities",
    "dim_entity_types",
    "fact_entity_events",
    "fact_entity_relationships",
    "fact_entity_states",
    "fact_tasks",
    "mart_entity_context",
    "mart_entity_open_loops",
    "mart_open_loops",
    "fact_decisions",
    "fact_risks",
    "mart_timeline",
)


def dashboard_status(
    *,
    state_dir: Path,
    postgres_dsn: str | None = None,
    raw_schema: str = "raw",
    mart_schema: str = "marts",
) -> dict[str, object]:
    replay_state = _read_json(state_dir / REPLAY_STATE_FILE)
    scheduler_state = _read_json(state_dir / SCHEDULER_STATE_FILE)
    postgres = _postgres_status(
        postgres_dsn=postgres_dsn,
        raw_schema=raw_schema,
        mart_schema=mart_schema,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state_dir": str(state_dir),
        "replay": _replay_summary(replay_state),
        "scheduler": _scheduler_summary(scheduler_state),
        "postgres": postgres,
        "readiness": _readiness(replay_state, scheduler_state, postgres),
    }


def serve_dashboard(
    *,
    host: str,
    port: int,
    state_dir: Path,
    postgres_dsn: str | None,
    raw_schema: str,
    mart_schema: str,
) -> None:
    handler = _handler(
        state_dir=state_dir,
        postgres_dsn=postgres_dsn,
        raw_schema=raw_schema,
        mart_schema=mart_schema,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Replay dashboard listening on http://{host}:{port}")
    server.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-replay-dashboard",
        description="Serve a local browser dashboard for replay and ingest/dbt status.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8083)
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("REPLAY_STATE_DIR", "var/replay-vault"),
        help="Replay target vault containing replay and scheduler state files.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("POSTGRES_DSN"),
        help="Optional Postgres DSN for raw and mart counts.",
    )
    parser.add_argument("--raw-schema", default=os.environ.get("POSTGRES_RAW_SCHEMA", "raw"))
    parser.add_argument("--mart-schema", default=os.environ.get("DBT_TARGET_SCHEMA", "marts"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    serve_dashboard(
        host=args.host,
        port=args.port,
        state_dir=Path(args.state_dir),
        postgres_dsn=args.postgres_dsn,
        raw_schema=args.raw_schema,
        mart_schema=args.mart_schema,
    )
    return 0


def _handler(
    *,
    state_dir: Path,
    postgres_dsn: str | None,
    raw_schema: str,
    mart_schema: str,
) -> type[BaseHTTPRequestHandler]:
    class ReplayDashboardHandler(BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/api/status"}:
                self.send_response(HTTPStatus.OK)
                content_type = (
                    "text/html; charset=utf-8"
                    if path == "/"
                    else "application/json; charset=utf-8"
                )
                self.send_header("Content-Type", content_type)
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
                payload = dashboard_status(
                    state_dir=state_dir,
                    postgres_dsn=postgres_dsn,
                    raw_schema=raw_schema,
                    mart_schema=mart_schema,
                )
                self._send_json(HTTPStatus.OK, payload)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

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

    return ReplayDashboardHandler


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _replay_summary(state: dict[str, object]) -> dict[str, object]:
    loaded = _int_value(state.get("loaded_count"))
    remaining = _int_value(state.get("remaining_count"))
    total = _int_value(state.get("total_count"))
    if not total and loaded is not None and remaining is not None:
        total = loaded + remaining
    progress = None
    if total and loaded is not None:
        progress = round((loaded / total) * 100, 1)
    return {
        "available": bool(state),
        "virtual_time": state.get("virtual_time"),
        "latest_loaded_timestamp": state.get("latest_loaded_timestamp"),
        "loaded_count": loaded,
        "remaining_count": remaining,
        "total_count": total,
        "progress_percent": progress,
        "source_root": state.get("source_root"),
        "target_root": state.get("target_root"),
    }


def _scheduler_summary(state: dict[str, object]) -> dict[str, object]:
    runs = state.get("runs") if isinstance(state.get("runs"), list) else []
    last_run = runs[-1] if runs else {}
    return {
        "available": bool(state),
        "status": state.get("status"),
        "updated_at": state.get("updated_at"),
        "run_count": state.get("run_count"),
        "last_success_at": state.get("last_success_at"),
        "last_virtual_time": state.get("last_virtual_time"),
        "last_loaded_count": state.get("last_loaded_count"),
        "last_remaining_count": state.get("last_remaining_count"),
        "last_run": last_run,
    }


def _postgres_status(
    *,
    postgres_dsn: str | None,
    raw_schema: str,
    mart_schema: str,
) -> dict[str, object]:
    if not postgres_dsn:
        return {"available": False, "error": "POSTGRES_DSN is not configured"}
    try:
        import psycopg

        with psycopg.connect(postgres_dsn) as connection:
            raw = _table_counts(connection, raw_schema, RAW_TABLES)
            marts = _table_counts(connection, mart_schema, MART_TABLES)
    except Exception as exc:  # pragma: no cover - exact psycopg errors vary.
        return {"available": False, "error": str(exc)}
    return {
        "available": True,
        "raw_schema": raw_schema,
        "mart_schema": mart_schema,
        "raw_counts": raw,
        "mart_counts": marts,
        "mcp_ready": bool(marts.get("mart_entity_context", 0) or marts.get("dim_entities", 0)),
    }


def _table_counts(connection: object, schema: str, tables: tuple[str, ...]) -> dict[str, int]:
    if not SCHEMA_RE.fullmatch(schema):
        raise ValueError(f"Invalid Postgres schema name: {schema}")
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute("select to_regclass(%s)", (f"{schema}.{table}",))
            exists = cursor.fetchone()[0]
            if not exists:
                counts[table] = 0
                continue
            cursor.execute(f'select count(*) from "{schema}"."{table}"')
            counts[table] = int(cursor.fetchone()[0])
    return counts


def _readiness(
    replay_state: dict[str, object],
    scheduler_state: dict[str, object],
    postgres: dict[str, object],
) -> dict[str, object]:
    checks = {
        "replay_state": bool(replay_state),
        "scheduler_state": bool(scheduler_state),
        "last_scheduler_run_success": scheduler_state.get("status") == "success",
        "postgres_available": postgres.get("available") is True,
        "marts_available": postgres.get("mcp_ready") is True,
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
    }


def _int_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Replay Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fa;
      --panel: #ffffff;
      --panel-2: #eef2f6;
      --text: #18212f;
      --muted: #657386;
      --line: #d8e0ea;
      --ok: #0f7b4f;
      --warn: #9a5b00;
      --bad: #b42318;
      --accent: #1f6feb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 15px; font-weight: 700; letter-spacing: 0; }
    main {
      max-width: 1240px;
      margin: 0 auto;
      padding: 20px;
      display: grid;
      gap: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .metric {
      min-height: 112px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; font-weight: 700; }
    .value { font-size: 28px; font-weight: 750; margin-top: 8px; overflow-wrap: anywhere; }
    .subtle { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 999px;
      padding: 4px 10px;
      font-weight: 700;
      background: var(--panel-2);
      color: var(--muted);
    }
    .status.ok { color: var(--ok); background: #e8f5ee; }
    .status.warn { color: var(--warn); background: #fff3d6; }
    .status.bad { color: var(--bad); background: #fdeceb; }
    .bar {
      height: 12px;
      border-radius: 999px;
      background: var(--panel-2);
      overflow: hidden;
      margin-top: 10px;
    }
    .bar > span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--accent);
      transition: width 200ms ease;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      padding: 8px 6px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    th { color: var(--muted); font-size: 12px; }
    code {
      background: var(--panel-2);
      border-radius: 4px;
      padding: 1px 4px;
      overflow-wrap: anywhere;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 220px;
      overflow: auto;
      background: #111827;
      color: #e5e7eb;
      padding: 12px;
      border-radius: 6px;
      font-size: 12px;
    }
    .two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    @media (max-width: 900px) {
      .grid, .two-col { grid-template-columns: 1fr; }
      header { padding: 16px; }
      main { padding: 16px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Replay Dashboard</h1>
      <div class="subtle">Generated-vault replay, scheduler, and Postgres mart freshness</div>
    </div>
    <div id="ready" class="status">Loading</div>
  </header>
  <main>
    <section class="grid">
      <div class="panel metric">
        <div><div class="label">Virtual Time</div><div id="virtualTime" class="value">-</div></div>
        <div id="latestLoaded" class="subtle">Latest loaded: -</div>
      </div>
      <div class="panel metric">
        <div><div class="label">Replay Loaded</div><div id="loaded" class="value">-</div></div>
        <div><div class="bar"><span id="progressBar"></span></div><div id="progress" class="subtle">-</div></div>
      </div>
      <div class="panel metric">
        <div><div class="label">Scheduler</div><div id="schedulerStatus" class="value">-</div></div>
        <div id="lastSuccess" class="subtle">Last success: -</div>
      </div>
      <div class="panel metric">
        <div><div class="label">MCP Readiness</div><div id="mcpReady" class="value">-</div></div>
        <div id="generatedAt" class="subtle">Updated: -</div>
      </div>
    </section>

    <section class="two-col">
      <div class="panel">
        <h2>Raw Tables</h2>
        <table><thead><tr><th>Table</th><th>Rows</th></tr></thead><tbody id="rawCounts"></tbody></table>
      </div>
      <div class="panel">
        <h2>Mart Tables</h2>
        <table><thead><tr><th>Table</th><th>Rows</th></tr></thead><tbody id="martCounts"></tbody></table>
      </div>
    </section>

    <section class="panel">
      <h2>Last Ingest/dbt Run</h2>
      <table>
        <tbody id="runDetails"></tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Last Error Or Command Output</h2>
      <pre id="commandOutput">Loading...</pre>
    </section>
  </main>
  <script>
    const fmt = value => value === null || value === undefined || value === "" ? "-" : String(value);
    const num = value => value === null || value === undefined ? "-" : Number(value).toLocaleString();
    function statusClass(ok, warn) {
      if (ok) return "status ok";
      if (warn) return "status warn";
      return "status bad";
    }
    function rowsFromCounts(counts) {
      return Object.entries(counts || {}).map(([name, count]) =>
        `<tr><td><code>${name}</code></td><td>${num(count)}</td></tr>`
      ).join("") || "<tr><td colspan='2'>No counts available</td></tr>";
    }
    async function refresh() {
      const response = await fetch("/api/status", { cache: "no-store" });
      const data = await response.json();
      const replay = data.replay || {};
      const scheduler = data.scheduler || {};
      const postgres = data.postgres || {};
      const readiness = data.readiness || {};
      const lastRun = scheduler.last_run || {};
      const progress = replay.progress_percent ?? 0;

      document.getElementById("ready").className = statusClass(readiness.ready, scheduler.available);
      document.getElementById("ready").textContent = readiness.ready ? "Ready" : "Not ready";
      document.getElementById("virtualTime").textContent = fmt(replay.virtual_time);
      document.getElementById("latestLoaded").textContent = `Latest loaded: ${fmt(replay.latest_loaded_timestamp)}`;
      document.getElementById("loaded").textContent = `${num(replay.loaded_count)} / ${num(replay.total_count)}`;
      document.getElementById("progress").textContent = `${fmt(replay.progress_percent)}% loaded, ${num(replay.remaining_count)} remaining`;
      document.getElementById("progressBar").style.width = `${Math.max(0, Math.min(100, progress))}%`;
      document.getElementById("schedulerStatus").textContent = fmt(scheduler.status);
      document.getElementById("lastSuccess").textContent = `Last success: ${fmt(scheduler.last_success_at)}`;
      document.getElementById("mcpReady").textContent = postgres.mcp_ready ? "Ready" : "Waiting";
      document.getElementById("generatedAt").textContent = `Updated: ${fmt(data.generated_at)}`;
      document.getElementById("rawCounts").innerHTML = rowsFromCounts(postgres.raw_counts);
      document.getElementById("martCounts").innerHTML = rowsFromCounts(postgres.mart_counts);
      document.getElementById("runDetails").innerHTML = [
        ["Run", lastRun.run_number],
        ["Status", lastRun.status],
        ["Started", lastRun.started_at],
        ["Finished", lastRun.finished_at],
        ["Duration seconds", lastRun.duration_seconds],
        ["Replay watermark", lastRun.virtual_time],
        ["Loaded / remaining", `${num(lastRun.loaded_count)} / ${num(lastRun.remaining_count)}`],
        ["Ingest return code", lastRun.ingest && lastRun.ingest.returncode],
        ["dbt return code", lastRun.dbt && lastRun.dbt.returncode]
      ].map(([label, value]) => `<tr><th>${label}</th><td>${fmt(value)}</td></tr>`).join("");
      const output = lastRun.error ||
        (lastRun.dbt && (lastRun.dbt.stderr || lastRun.dbt.stdout)) ||
        (lastRun.ingest && (lastRun.ingest.stderr || lastRun.ingest.stdout)) ||
        postgres.error ||
        "No command output available.";
      document.getElementById("commandOutput").textContent = output;
    }
    refresh().catch(error => {
      document.getElementById("ready").className = "status bad";
      document.getElementById("ready").textContent = "Error";
      document.getElementById("commandOutput").textContent = error.message;
    });
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
