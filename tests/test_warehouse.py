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
    assert {"entity_type": "person", "count": 16} in summary["entity_types"]

    note = warehouse.connection.execute(
        """
        select
            source_date,
            source_created_at,
            source_observed_at,
            created_at,
            updated_at
        from dim_notes
        where source_path = 'Meetings/Horizon Kickoff.md'
        """
    ).fetchone()
    assert note == {
        "source_date": "2026-06-01",
        "source_created_at": "2026-06-01T11:13:00",
        "source_observed_at": "2026-06-01T14:03:00",
        "created_at": "2026-06-01T16:39:00",
        "updated_at": "2026-06-01T17:39:00",
    }

    entity_note = warehouse.connection.execute(
        """
        select source_date, created_at
        from dim_notes
        where source_path = 'People/Morgan Lee.md'
        """
    ).fetchone()
    assert entity_note == {
        "source_date": None,
        "created_at": "2026-05-13T11:35:00",
    }


def test_warehouse_lists_typed_entities_from_notes_and_links():
    context = build_context(VaultConfig(vault_path=Path("examples/synthetic-vault")))
    warehouse = build_warehouse(context)

    people = list_entities(warehouse, entity_type="person")
    projects = list_entities(warehouse, entity_type="project")

    assert {"Morgan Lee", "Priya Shah", "Elena Rostova", "Marcus Vance"}.issubset(
        {entity["name"] for entity in people}
    )
    assert {"Project Atlas", "Project Pipeline", "Project Horizon"}.issubset(
        {entity["name"] for entity in projects}
    )


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
