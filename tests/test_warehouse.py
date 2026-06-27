from pathlib import Path

from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import (
    agent_context,
    build_warehouse,
    entity_timeline,
    list_entities,
    warehouse_summary,
)


def test_warehouse_builds_dimensional_model_from_synthetic_vault():
    context = build_context(VaultConfig(vault_path=Path("examples/synthetic-vault")))
    warehouse = build_warehouse(context)

    summary = warehouse_summary(warehouse)

    assert summary["tables"]["dim_notes"] >= 10
    assert summary["tables"]["fact_blocks"] >= 10
    assert summary["tables"]["mart_timeline"] >= summary["tables"]["fact_tasks"]
    assert {"entity_type": "person", "count": 2} in summary["entity_types"]


def test_warehouse_lists_typed_entities_from_notes_and_links():
    context = build_context(VaultConfig(vault_path=Path("examples/synthetic-vault")))
    warehouse = build_warehouse(context)

    people = list_entities(warehouse, entity_type="person")
    projects = list_entities(warehouse, entity_type="project")

    assert {entity["name"] for entity in people} == {"Morgan Lee", "Priya Shah"}
    assert {entity["name"] for entity in projects} == {"Project Atlas"}


def test_entity_timeline_returns_provenance_backed_rows():
    context = build_context(VaultConfig(vault_path=Path("examples/synthetic-vault")))
    warehouse = build_warehouse(context)

    rows = entity_timeline(warehouse, entity="Morgan Lee", limit=100)

    assert rows
    assert any(row["source_path"] == "Meetings/Atlas Renewal Review.md" for row in rows)
    assert all("source_path" in row and "start_line" in row for row in rows)


def test_agent_context_can_filter_open_tasks_by_entity():
    context = build_context(VaultConfig(vault_path=Path("examples/synthetic-vault")))
    warehouse = build_warehouse(context)

    rows = agent_context(
        warehouse,
        entity="Renewal Prep Scope",
        event_type="task_open",
        limit=100,
    )

    assert rows
    assert all(row["event_type"] == "task_open" for row in rows)
