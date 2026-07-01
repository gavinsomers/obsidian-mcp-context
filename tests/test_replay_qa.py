from __future__ import annotations

import json
from pathlib import Path
import threading
from urllib.request import Request, urlopen

from obsidian_mcp_context.ai import AICompletionResult, AIProviderError
from obsidian_mcp_context.config import AppConfig
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


class FakePagedMartService(FakeMartService):
    def list_entities(
        self,
        vault_path: str | Path,
        entity_type: str | None = None,
        text: str | None = None,
        limit: int = 100,
        postgres_dsn: str | Path | None = None,
    ) -> list[dict[str, object]]:
        if text is None:
            return [
                {
                    "entity_id": "company:apex",
                    "entity_type": "company",
                    "name": "Apex Analytics",
                    "source_path": "Companies/Apex Analytics.md",
                }
            ]
        if text == "Project Atlas 1":
            return [
                {
                    "entity_id": "decision:atlas-1",
                    "entity_type": "decision",
                    "name": "Project Atlas 1 Security Review Decision 1",
                    "source_path": "Decisions/Project Atlas 1 Security Review Decision 1.md",
                },
                {
                    "entity_id": "project:atlas-1",
                    "entity_type": "project",
                    "name": "Project Atlas 1",
                    "source_path": "Projects/Project Atlas 1.md",
                },
            ]
        return []

    def agent_context(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("broad fallback context should not be used")


class FakeAccountMartService(FakeMartService):
    app_config = AppConfig(
        replay_qa_entity_type_preferences=("account", "client", "case")
    )

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
                "entity_id": "company:acme",
                "entity_type": "company",
                "name": "Acme",
                "source_path": "Companies/Acme.md",
            },
            {
                "entity_id": "account:acme",
                "entity_type": "account",
                "name": "Acme",
                "source_path": "Accounts/Acme.md",
            },
        ]

    def entity_context_generic(
        self,
        postgres_dsn: str | Path | None,
        entity_type: str,
        entity: str,
        limit: int,
    ) -> list[dict[str, object]]:
        assert entity_type == "account"
        assert entity == "Acme"
        return [
            {
                "row_id": "account:acme:context",
                "event_date": "2026-01-10",
                "event_type": "entity_context",
                "source_path": "Accounts/Acme.md",
                "start_line": 7,
                "title": "Acme account state",
                "summary": "Acme account onboarding is ready for review.",
            }
        ]

    def project_context(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("account Q&A should use generic entity context")

    def person_context(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("account Q&A should use generic entity context")


class FakeSummaryProvider:
    provider = "ollama"
    model = "gemma4:26b-a4b-it-q4_K_M"

    def __init__(
        self,
        *,
        answer: str = "Gemma summary from evidence [1] [2].",
        fail: bool = False,
    ) -> None:
        self.answer = answer
        self.fail = fail
        self.prompts: list[str] = []

    def complete_json(
        self,
        prompt: str,
        schema: dict[str, object],
        *,
        max_context_chars: int,
        prompt_version: str,
    ) -> AICompletionResult:
        self.prompts.append(prompt)
        if self.fail:
            raise AIProviderError("ollama unavailable")
        if len(prompt) > max_context_chars:
            from obsidian_mcp_context.ai import ContextOverflowError

            raise ContextOverflowError("too much context")
        return AICompletionResult(
            data={"answer": self.answer, "citations": [1, 2]},
            provider=self.provider,
            model=self.model,
            prompt_version=prompt_version,
            input_hash="hash",
            created_at="2026-06-30T21:30:00+00:00",
        )


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
    assert answer["summary"]["status"] == "not_requested"


def test_answer_question_finds_project_when_initial_entity_page_misses_it(
    tmp_path,
    monkeypatch,
):
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
        service=FakePagedMartService(),
    )

    assert answer["status"] == "ok"
    assert answer["mode"] == "mart-backed"
    assert answer["entity"]["entity_type"] == "project"
    assert answer["entity"]["name"] == "Project Atlas 1"


def test_answer_question_uses_profile_entity_type_preferences_for_accounts(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "obsidian_mcp_context.replay_qa.dashboard_status",
        lambda **_: {
            "replay": {"virtual_time": "2026-01-10T09:00:00"},
            "readiness": {"ready": True},
        },
    )

    answer = answer_question(
        "What is the latest context for Acme?",
        vault_path=tmp_path,
        state_dir=tmp_path,
        postgres_dsn="postgres://example",
        service=FakeAccountMartService(),
    )

    assert answer["status"] == "ok"
    assert answer["mode"] == "mart-backed"
    assert answer["entity"]["entity_type"] == "account"
    assert answer["entity"]["name"] == "Acme"
    assert answer["rows"][0]["source_path"] == "Accounts/Acme.md"


def test_answer_question_can_summarize_retrieved_rows_with_local_provider(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "obsidian_mcp_context.replay_qa.dashboard_status",
        lambda **_: {
            "replay": {"virtual_time": "2023-04-21T09:00:00"},
            "readiness": {"ready": True},
        },
    )
    summarizer = FakeSummaryProvider()

    answer = answer_question(
        "What are the risks and open loops for Project Atlas 1?",
        vault_path=tmp_path,
        state_dir=tmp_path,
        postgres_dsn="postgres://example",
        service=FakeMartService(),
        summarize=True,
        summarizer=summarizer,
    )

    assert answer["status"] == "ok"
    assert answer["mode"] == "mart-backed+local-gemma"
    assert answer["answer"] == "Gemma summary from evidence [1] [2]."
    assert "Enablement owner is not confirmed." in summarizer.prompts[0]
    assert "Risks/Project Atlas 1 Adoption Workflow Risk 1.md" in summarizer.prompts[0]
    assert answer["deterministic_answer"].startswith("Mart-backed context")
    assert answer["summary"] == {
        "enabled": True,
        "status": "ok",
        "provider": "ollama",
        "model": "gemma4:26b-a4b-it-q4_K_M",
        "prompt_version": "replay-qa-summary-v1",
        "input_hash": "hash",
        "created_at": "2026-06-30T21:30:00+00:00",
        "citations": [1, 2],
    }


def test_answer_question_keeps_deterministic_answer_when_summary_provider_fails(
    tmp_path,
    monkeypatch,
):
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
        summarize=True,
        summarizer=FakeSummaryProvider(fail=True),
    )

    assert answer["mode"] == "mart-backed"
    assert answer["summary"]["status"] == "provider_error"
    assert answer["summary"]["error"] == "ollama unavailable"
    assert answer["answer"] == answer["deterministic_answer"]


def test_answer_question_reports_summary_context_overflow(tmp_path, monkeypatch):
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
        summarize=True,
        summarizer=FakeSummaryProvider(),
        summary_max_context_chars=10,
    )

    assert answer["mode"] == "mart-backed"
    assert answer["summary"]["status"] == "context_overflow"
    assert answer["answer"] == answer["deterministic_answer"]


def test_answer_question_skips_summary_when_no_evidence_is_retrieved(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "obsidian_mcp_context.replay_qa.dashboard_status",
        lambda **_: {
            "replay": {"virtual_time": "2023-04-21T09:00:00"},
            "readiness": {"ready": True},
        },
    )

    answer = answer_question(
        "Unknown portfolio question",
        vault_path=tmp_path,
        state_dir=tmp_path,
        postgres_dsn="postgres://example",
        service=FakeMartService(),
        summarize=True,
        summarizer=FakeSummaryProvider(),
    )

    assert answer["status"] == "no_match"
    assert answer["summary"]["enabled"] is True
    assert answer["summary"]["status"] == "no_evidence"


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
    assert answer["summary"]["status"] == "not_available"


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
        summarizer=FakeSummaryProvider(),
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
            data=json.dumps(
                {"question": "risks for Project Atlas 1", "summarize": True}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = json.loads(urlopen(request, timeout=2).read().decode())
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert "Replay Q&A" in html
    assert payload["mode"] == "mart-backed+local-gemma"
    assert payload["entity"]["name"] == "Project Atlas 1"
    assert payload["summary"]["status"] == "ok"
