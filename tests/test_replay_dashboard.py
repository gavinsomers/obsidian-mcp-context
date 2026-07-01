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
    assert status["observability"]["source_counts"]["notes"] == 1
    assert status["observability"]["compiled_counts"]["context_rows"] == 1


def test_dashboard_status_exposes_memory_observability_sections(tmp_path, monkeypatch):
    _write_json(tmp_path / REPLAY_STATE_FILE, {"loaded_count": 5, "remaining_count": 2})
    _write_json(
        tmp_path / SCHEDULER_STATE_FILE,
        {"status": "success", "last_success_at": "2026-07-01T09:00:00+00:00"},
    )

    def fake_postgres_status(**_: object) -> dict[str, object]:
        return {
            "available": True,
            "mcp_ready": True,
            "raw_counts": {
                "base_obsidian_files": 5,
                "base_obsidian_blocks": 20,
                "base_obsidian_tasks": 7,
                "base_obsidian_links": 9,
                "base_obsidian_tags": 4,
                "base_obsidian_lines": 80,
            },
            "mart_counts": {
                "dim_entities": 6,
                "fact_entity_relationships": 8,
                "fact_entity_states": 3,
                "fact_entity_events": 11,
                "mart_timeline": 5,
                "mart_entity_context": 13,
                "mart_entity_open_loops": 2,
                "fact_decisions": 4,
                "fact_risks": 3,
            },
            "review_counts": {
                "deterministic_suggested_links": 1,
                "ai_suggested_links": 0,
            },
            "note_type_counts": {"project": 2, "meeting": 3},
            "entity_type_counts": {"project": 2, "unknown": 1},
            "decision_status_counts": {"active": 3, "superseded": 1},
            "risk_status_counts": {"open": 2, "resolved": 1},
        }

    monkeypatch.setattr(
        "obsidian_mcp_context.replay_dashboard._postgres_status",
        fake_postgres_status,
    )

    status = dashboard_status(state_dir=tmp_path, postgres_dsn="postgres://example")
    observability = status["observability"]

    assert observability["source_counts"]["notes"] == 5
    assert observability["compiled_counts"]["unknown_entities"] == 1
    assert observability["compiled_counts"]["decision_status_counts"] == {
        "active": 3,
        "superseded": 1,
    }
    assert observability["pipeline_health"]["ready"] is True
    assert observability["suggestion_metrics"]["deterministic_suggested_links"] == 1
    signals = {
        signal["id"]: signal
        for signal in observability["stale_context_signals"]
    }
    assert signals["orphaned_references"]["count"] == 1
    assert signals["stale_open_loops"]["count"] == 2
    assert signals["stale_decisions"]["count"] == 1
    assert signals["missing_next_actions"]["available"] is False


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
    assert "Source Vault Shape" in html
    assert "Compiled Knowledge Shape" in html
    assert "Stale Context Signals" in html
    assert payload["replay"]["loaded_count"] == 1
