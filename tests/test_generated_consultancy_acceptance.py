from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from obsidian_mcp_context import mcp_server
from obsidian_mcp_context.services import ContextService
from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import (
    Warehouse,
    agent_context,
    build_warehouse,
    entity_timeline,
    list_entities,
)


GENERATED_MEDIUM_VAULT = Path("examples/generated-vaults/medium")
ATLAS_1 = "Project Atlas 1"
ATLAS_VARIANTS = {"Project Atlas 16", "Project Atlas 31", "Project Atlas 46"}


@pytest.fixture(scope="module")
def generated_medium_warehouse() -> Warehouse:
    context = build_context(VaultConfig(vault_path=GENERATED_MEDIUM_VAULT))
    warehouse = build_warehouse(context)
    yield warehouse
    warehouse.close()


def _contains_atlas_variant(row: dict[str, object]) -> bool:
    haystack = "\n".join(str(value) for value in row.values())
    return any(variant in haystack for variant in ATLAS_VARIANTS)


def test_generated_project_atlas_1_parser_context_is_exactly_disambiguated(
    generated_medium_warehouse: Warehouse,
):
    matching_projects = {
        row["name"]
        for row in list_entities(
            generated_medium_warehouse,
            entity_type="project",
            text="Project Atlas",
            limit=25,
        )
    }
    assert {ATLAS_1, *ATLAS_VARIANTS}.issubset(matching_projects)

    rows = entity_timeline(generated_medium_warehouse, entity=ATLAS_1, limit=500)
    assert rows
    assert not any(_contains_atlas_variant(row) for row in rows)

    expected_timeline_rows = {
        (
            "Projects/Project Atlas 1.md",
            None,
            "block",
            "## Overview\nProject Atlas 1 supports [[Northstar Labs]] through consulting delivery.",
        ),
        (
            "Meetings/Project Atlas 1 Warehouse Mapping Sync 1.md",
            "2023-05-20",
            "block",
            "## Notes\nWarehouse Mapping reviewed for [[Project Atlas 1]] at [[Northstar Labs]].\n[[Alex Alvarez]] flagged follow-up work for the next operating review.",
        ),
        (
            "Decisions/Project Atlas 1 Security Review Decision 1.md",
            "2023-06-10",
            "task_open",
            "Review whether [[Project Atlas 1 Security Review Decision 1]] changes open loops for [[Project Atlas 1]] #follow-up",
        ),
        (
            "Risks/Project Atlas 1 Adoption Workflow Risk 1.md",
            None,
            "block",
            "## Risk\nAdoption Workflow may affect [[Project Atlas 1]] for [[Northstar Labs]].",
        ),
        (
            "Research/Project Atlas 1 Contract Renewal Research 1.md",
            None,
            "task_open",
            "Convert findings into decision criteria for [[Project Atlas 1]] #research",
        ),
    }
    actual_timeline_rows = {
        (
            row["source_path"],
            row["event_date"],
            row["event_type"],
            row["summary"],
        )
        for row in rows
    }

    assert expected_timeline_rows.issubset(actual_timeline_rows)


def test_generated_project_atlas_1_open_loop_query_keeps_source_provenance(
    generated_medium_warehouse: Warehouse,
):
    rows = agent_context(
        generated_medium_warehouse,
        entity=ATLAS_1,
        event_type="task_open",
        limit=200,
    )

    expected_open_loops = {
        (
            "Meetings/Project Atlas 1 Warehouse Mapping Sync 1.md",
            24,
            "Send recap for [[Project Atlas 1]] to [[Alex Alvarez]] #follow-up",
        ),
        (
            "Decisions/Project Atlas 1 Security Review Decision 1.md",
            27,
            "Review whether [[Project Atlas 1 Security Review Decision 1]] changes open loops for [[Project Atlas 1]] #follow-up",
        ),
        (
            "Research/Project Atlas 1 Contract Renewal Research 1.md",
            21,
            "Convert findings into decision criteria for [[Project Atlas 1]] #research",
        ),
    }
    actual_open_loops = {
        (row["source_path"], row["start_line"], row["summary"]) for row in rows
    }

    assert expected_open_loops.issubset(actual_open_loops)
    assert not any(_contains_atlas_variant(row) for row in rows)


class FakeDbtWarehouse:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_entities(
        self,
        handle: str,
        text: str | None = None,
        limit: int = 500,
        **_: object,
    ) -> list[dict[str, object]]:
        self.calls.append(("list_entities", {"text": text, "limit": limit}))
        return [
            {"entity_type": "project", "name": "Project Atlas 16"},
            {"entity_type": "project", "name": ATLAS_1},
            {"entity_type": "project", "name": "Project Atlas 31"},
        ]

    def project_context(
        self,
        handle: str,
        project: str,
        limit: int,
    ) -> list[dict[str, object]]:
        self.calls.append(("project_context", {"project": project, "limit": limit}))
        return [{"event_type": "decision_superseded", "related_entities": project}]

    def list_decisions(
        self,
        handle: str,
        entity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                "list_decisions",
                {"entity": entity, "status": status, "limit": limit},
            )
        )
        return [{"title": "Project Atlas 1 Security Review Decision 1"}]

    def list_risks(
        self,
        handle: str,
        entity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self.calls.append(
            ("list_risks", {"entity": entity, "status": status, "limit": limit})
        )
        return [{"title": "Project Atlas 1 Adoption Workflow Risk 1"}]

    def list_open_loops(
        self,
        handle: str,
        entity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self.calls.append(("list_open_loops", {"entity": entity, "limit": limit}))
        return [{"summary": "Send recap for [[Project Atlas 1]] to [[Alex Alvarez]]"}]


@dataclass(frozen=True)
class PromptGolden:
    prompt: str
    call: Callable[[ContextService], list[dict[str, object]]]
    expected_calls: list[tuple[str, dict[str, object]]]


def test_prompt_to_service_query_goldens_use_exact_project_atlas_1(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_warehouse = FakeDbtWarehouse()
    service = ContextService()
    monkeypatch.setattr(
        service,
        "dbt_reader",
        lambda postgres_dsn=None: (fake_warehouse, "postgres://fixture"),
    )

    goldens = [
        PromptGolden(
            prompt="What is the full Project Atlas 1 context?",
            call=lambda svc: svc.agent_context(
                GENERATED_MEDIUM_VAULT,
                entity=ATLAS_1,
                limit=25,
                postgres_dsn="postgres://fixture",
            ),
            expected_calls=[
                ("list_entities", {"text": ATLAS_1, "limit": 500}),
                ("project_context", {"project": ATLAS_1, "limit": 25}),
            ],
        ),
        PromptGolden(
            prompt="Show decisions for Project Atlas 1.",
            call=lambda svc: svc.decisions(
                "postgres://fixture",
                entity=ATLAS_1,
                limit=25,
            ),
            expected_calls=[
                (
                    "list_decisions",
                    {"entity": ATLAS_1, "status": None, "limit": 25},
                )
            ],
        ),
        PromptGolden(
            prompt="Show open risks for Project Atlas 1.",
            call=lambda svc: svc.risks(
                "postgres://fixture",
                entity=ATLAS_1,
                status="open",
                limit=25,
            ),
            expected_calls=[
                (
                    "list_risks",
                    {"entity": ATLAS_1, "status": "open", "limit": 25},
                )
            ],
        ),
        PromptGolden(
            prompt="What open loops remain for Project Atlas 1?",
            call=lambda svc: svc.open_loops(
                "postgres://fixture",
                entity=ATLAS_1,
                limit=25,
            ),
            expected_calls=[
                ("list_open_loops", {"entity": ATLAS_1, "limit": 25})
            ],
        ),
    ]

    for golden in goldens:
        before = len(fake_warehouse.calls)
        rows = golden.call(service)
        assert rows, golden.prompt
        assert fake_warehouse.calls[before:] == golden.expected_calls, golden.prompt


class FakeMcpContextService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def project_context(
        self,
        postgres_dsn: str | None,
        project: str,
        limit: int,
    ) -> list[dict[str, object]]:
        self.calls.append(("project_context", {"project": project, "limit": limit}))
        return [{"related_entities": project}]

    def decisions(
        self,
        postgres_dsn: str | None,
        entity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                "decisions",
                {"entity": entity, "status": status, "limit": limit},
            )
        )
        return [{"related_entities": entity}]

    def risks(
        self,
        postgres_dsn: str | None,
        entity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self.calls.append(("risks", {"entity": entity, "status": status, "limit": limit}))
        return [{"related_entities": entity}]

    def open_loops(
        self,
        postgres_dsn: str | None,
        entity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self.calls.append(("open_loops", {"entity": entity, "limit": limit}))
        return [{"related_entities": entity}]


def test_mcp_project_atlas_1_tools_pass_exact_entity_filters(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_service = FakeMcpContextService()
    monkeypatch.setattr(mcp_server, "default_context_service", fake_service)
    vault_path = str(GENERATED_MEDIUM_VAULT)

    assert mcp_server.get_vault_project_context(vault_path, project=ATLAS_1, limit=25)
    assert mcp_server.list_vault_decisions(vault_path, entity=ATLAS_1, limit=25)
    assert mcp_server.list_vault_risks(
        vault_path,
        entity=ATLAS_1,
        status="open",
        limit=25,
    )
    assert mcp_server.list_vault_open_loops(vault_path, entity=ATLAS_1, limit=25)

    assert fake_service.calls == [
        ("project_context", {"project": ATLAS_1, "limit": 25}),
        ("decisions", {"entity": ATLAS_1, "status": None, "limit": 25}),
        ("risks", {"entity": ATLAS_1, "status": "open", "limit": 25}),
        ("open_loops", {"entity": ATLAS_1, "limit": 25}),
    ]
