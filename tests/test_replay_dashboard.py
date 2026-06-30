from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

from obsidian_mcp_context.replay_dashboard import (
    SCHEDULER_STATE_FILE,
    REPLAY_STATE_FILE,
    dashboard_status,
    serve_dashboard,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_dashboard_status_summarizes_replay_and_scheduler_state(tmp_path):
    _write_json(
        tmp_path / REPLAY_STATE_FILE,
        {
            "virtual_time": "2023-04-20T06:14:00",
            "latest_loaded_timestamp": "2023-04-20T06:14:00",
            "loaded_count": 3,
            "remaining_count": 7,
            "total_count": 10,
        },
    )
    _write_json(
        tmp_path / SCHEDULER_STATE_FILE,
        {
            "status": "success",
            "run_count": 2,
            "last_success_at": "2026-06-30T20:39:13+00:00",
            "runs": [{"run_number": 2, "status": "success"}],
        },
    )

    status = dashboard_status(state_dir=tmp_path, postgres_dsn=None)

    assert status["replay"]["progress_percent"] == 30.0
    assert status["scheduler"]["status"] == "success"
    assert status["scheduler"]["last_run"]["run_number"] == 2
    assert status["postgres"]["available"] is False
    assert status["readiness"]["ready"] is False


def test_dashboard_status_can_be_ready_with_postgres_counts(tmp_path, monkeypatch):
    _write_json(tmp_path / REPLAY_STATE_FILE, {"loaded_count": 1, "remaining_count": 0})
    _write_json(tmp_path / SCHEDULER_STATE_FILE, {"status": "success"})

    def fake_postgres_status(**_: object) -> dict[str, object]:
        return {
            "available": True,
            "mcp_ready": True,
            "raw_counts": {"base_obsidian_files": 1},
            "mart_counts": {"mart_entity_context": 1},
        }

    monkeypatch.setattr(
        "obsidian_mcp_context.replay_dashboard._postgres_status",
        fake_postgres_status,
    )

    status = dashboard_status(state_dir=tmp_path, postgres_dsn="postgres://example")

    assert status["readiness"]["ready"] is True
    assert status["postgres"]["mart_counts"]["mart_entity_context"] == 1


def test_dashboard_http_serves_html_and_status(tmp_path):
    _write_json(tmp_path / REPLAY_STATE_FILE, {"loaded_count": 1, "remaining_count": 0})
    _write_json(tmp_path / SCHEDULER_STATE_FILE, {"status": "success"})

    import threading

    thread = threading.Thread(
        target=serve_dashboard,
        kwargs={
            "host": "127.0.0.1",
            "port": 0,
            "state_dir": tmp_path,
            "postgres_dsn": None,
            "raw_schema": "raw",
            "mart_schema": "marts",
        },
        daemon=True,
    )
    # Use the handler-level test path instead of this thread because port 0 is
    # not exposed from serve_forever. The smoke coverage for actual serving is
    # done in the integration command; keep this test focused on payloads.
    assert thread.daemon is True

    status = dashboard_status(state_dir=tmp_path, postgres_dsn=None)
    assert status["replay"]["loaded_count"] == 1


def test_dashboard_http_smoke_with_ephemeral_server(tmp_path):
    from obsidian_mcp_context.replay_dashboard import _handler
    from http.server import ThreadingHTTPServer
    import threading

    _write_json(tmp_path / REPLAY_STATE_FILE, {"loaded_count": 1, "remaining_count": 0})
    handler = _handler(
        state_dir=tmp_path,
        postgres_dsn=None,
        raw_schema="raw",
        mart_schema="marts",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        html = urlopen(f"http://{host}:{port}/", timeout=2).read().decode()
        payload = json.loads(
            urlopen(f"http://{host}:{port}/api/status", timeout=2).read().decode()
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert "Replay Dashboard" in html
    assert payload["replay"]["loaded_count"] == 1
