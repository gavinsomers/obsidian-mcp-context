from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import duckdb

from obsidian_mcp_context import dbt_warehouse
from obsidian_mcp_context.status import STATUS_TABLES, warehouse_status
from obsidian_mcp_context.web_ui import ContextHandler


def _write_status_warehouse(path: Path) -> None:
    tables = sorted(dbt_warehouse.REQUIRED_MARTS | set(STATUS_TABLES))
    connection = duckdb.connect(str(path))
    try:
        for table in tables:
            connection.execute(f"create table {table} (id text)")
        for table in STATUS_TABLES:
            connection.execute(f"insert into {table} values ('{table}:1')")
    finally:
        connection.close()


def test_warehouse_status_reports_snapshot_counts_and_simulation_state(tmp_path: Path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    (vault_path / "Note.md").write_text("# Note\n", encoding="utf-8")
    writer_path = tmp_path / "obsidian.duckdb"
    read_path = tmp_path / "obsidian-read.duckdb"
    state_path = tmp_path / "simulation-state.json"
    _write_status_warehouse(writer_path)
    _write_status_warehouse(read_path)
    state_path.write_text(
        json.dumps(
            {
                "virtual_date": "2026-06-18",
                "start_date": "2026-05-01",
                "end_date": "2026-07-14",
                "run_number": 4,
                "last_released_count": 12,
                "total_released_count": 56,
                "complete": False,
            }
        ),
        encoding="utf-8",
    )

    status = warehouse_status(
        vault_path,
        active_duckdb_path=read_path,
        writer_duckdb_path=writer_path,
        read_duckdb_path=read_path,
        simulation_state_path=state_path,
    )

    assert status["vault"]["markdown_file_count"] == 1
    assert status["warehouse"]["active_reader"]["available"] is True
    assert status["warehouse"]["reading_from_stable_snapshot"] is True
    assert status["warehouse"]["row_counts"]["dim_notes"] == 1
    assert status["warehouse"]["missing_required_marts"] == []
    assert status["simulation"]["state"]["virtual_date"] == "2026-06-18"
    assert status["simulation"]["state"]["run_number"] == 4


def test_web_status_endpoint_returns_status_json(tmp_path: Path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    read_path = tmp_path / "obsidian-read.duckdb"
    _write_status_warehouse(read_path)
    handler = type(
        "TestContextHandler",
        (ContextHandler,),
        {"vault_path": vault_path, "duckdb_path": read_path},
    )

    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload["warehouse"]["active_reader"]["available"] is True
    assert payload["warehouse"]["row_counts"]["mart_open_loops"] == 1
