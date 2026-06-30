from __future__ import annotations

import json
from pathlib import Path
import threading
from urllib.request import Request, urlopen

from obsidian_mcp_context.replay_dashboard import REPLAY_STATE_FILE, SCHEDULER_STATE_FILE
from obsidian_mcp_context.replay_qa import answer_question, _handler


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class FakeMartService:
    def dbt_reader(self, postgres_dsn: str | None = None) -> tuple[object, str]:
        return (object(), postgres_dsn or "postgres://example")

    def list_entities(
        self,
        vault_path: str | Path,
        entity_type: str | None = None,
        text: str | None = None,
        limit: int = 100,
        postgres_dsn: str | Path | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "entity_id": "project:atlas-1",
                "entity_type": "project",
                "name": "Project Atlas 1",
                "source_path": "Projects/Project Atlas 1.md",
            },
            {
                "entity_id": "project:atlas-10",
                "entity_type": "project",
                "name": "Project Atlas 10",
                "source_path": "Projects/Project Atlas 10.md",
            },
        ]

    def risks(
        self,
        postgres_dsn: str | Path | None,
        entity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        assert entity == "Project Atlas 1"
        return [
            {
                "row_id": "risk:1",
                "event_date": "2023-04-20",
                "event_type": "risk_open",
                "source_path": "Risks/Project Atlas 1 Adoption Workflow Risk 1.md",
                "start_line": None,
                "title": "Adoption workflow risk",
                "summary": "Enablement owner is not confirmed.",
            }
        ]

    def open_loops(
        self,
        postgres_dsn: str | Path | None,
        entity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        assert entity == "Project Atlas 1"
        return [
            {
                "row_id": "open_loop:1",
                "event_date": "2023-04-21",
                "event_type": "open_loop",
                "source_path": "Daily/2023-04-21.md",
                "start_line": 12,
                "title": "Follow ups",
                "summary": "Confirm enablement owner with Alex Alvarez.",
            }
        ]

    def project_context(
        self,
        postgres_dsn: str | Path | None,
        project: str,
        limit: int,
    ) -> list[dict[str, object]]:
        assert project == "Project Atlas 1"
        return []

    def decisions(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        return []

    def person_context(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        return []

    def entity_context_generic(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        return []

    def agent_context(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        return []


class FakeFallbackService:
    def dbt_reader(self, postgres_dsn: str | None = None) -> None:
        return None

    def search_blocks(
        self,
        vault_path: str | Path,
        text: str | None = None,
        source_path: str | None = None,
        heading: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, object]]:
        return [
            {
                "source_path": "Projects/Project Atlas 1.md",
                "start_line": 3,
                "heading_path": "Status",
                "text": "Project Atlas 1 is in discovery.",
            }
        ]


def test_answer_question_uses_exact_mart_entity_and_sources(tmp_path, monkeypatch):
    _write_json(tmp_path / REPLAY_STATE_FILE, {"virtual_time": "2023-04-21T09:00:00"})
    _write_json(tmp_path / SCHEDULER_STATE_FILE, {"status": "success"})
    monkeypatch.setattr(
        "obsidian_mcp_context.replay_dashboard._postgres_status",
        lambda **_: {"available": True, "mcp_ready": True},
    )
    monkeypatch.setattr(
        "obsidian_mcp_context.replay_qa.dashboard_status",
        lambda **_: {
            "replay": {"virtual_time": "2023-04-21T09:00:00"},
            "readiness": {"ready": True},
        },
    )

    answer = answer_question(
        "What are the risks and open loops for Project Atlas 1?",
        vault_path=tmp_path,
        state_dir=tmp_path,
        postgres_dsn="postgres://example",
        service=FakeMartService(),
    )

    assert answer["status"] == "ok"
    assert answer["mode"] == "mart-backed"
    assert answer["entity"]["name"] == "Project Atlas 1"
    assert len(answer["rows"]) == 2
    assert {source["source_path"] for source in answer["sources"]} == {
        "Risks/Project Atlas 1 Adoption Workflow Risk 1.md",
        "Daily/2023-04-21.md",
    }
    assert "Project Atlas 10" not in answer["answer"]


def test_answer_question_reports_parser_diagnostic_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "obsidian_mcp_context.replay_qa.dashboard_status",
        lambda **_: {"postgres": {"available": False}, "readiness": {"ready": False}},
    )

    answer = answer_question(
        "Project Atlas 1",
        vault_path=tmp_path,
        state_dir=tmp_path,
        service=FakeFallbackService(),
    )

    assert answer["status"] == "fallback"
    assert answer["mode"] == "parser-diagnostic-fallback"
    assert answer["sources"][0]["source_path"] == "Projects/Project Atlas 1.md"


def test_replay_qa_http_smoke_with_ephemeral_server(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "obsidian_mcp_context.replay_qa.dashboard_status",
        lambda **_: {
            "replay": {"virtual_time": "2023-04-21T09:00:00"},
            "readiness": {"ready": True},
        },
    )
    handler = _handler(
        vault_path=tmp_path,
        state_dir=tmp_path,
        postgres_dsn="postgres://example",
        raw_schema="raw",
        mart_schema="marts",
        service=FakeMartService(),
    )

    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        html = urlopen(f"http://{host}:{port}/", timeout=2).read().decode()
        request = Request(
            f"http://{host}:{port}/api/ask",
            data=json.dumps({"question": "risks for Project Atlas 1"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = json.loads(urlopen(request, timeout=2).read().decode())
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert "Replay Q&A" in html
    assert payload["mode"] == "mart-backed"
    assert payload["entity"]["name"] == "Project Atlas 1"
