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


def test_entity_filters_match_exact_related_entity_names(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    (vault / "Daily").mkdir()
    (vault / "Projects" / "Project Atlas 1.md").write_text(
        "# Project Atlas 1\n", encoding="utf-8"
    )
    (vault / "Projects" / "Project Atlas 16.md").write_text(
        "# Project Atlas 16\n", encoding="utf-8"
    )
    (vault / "Daily" / "2025-01-01.md").write_text(
        "\n".join(
            [
                "# 2025-01-01",
                "## Atlas 1",
                "Checked [[Project Atlas 1]] today.",
                "",
                "## Atlas 16",
                "Checked [[Project Atlas 16]] today.",
            ]
        ),
        encoding="utf-8",
    )

    context = build_context(VaultConfig(vault_path=vault))
    warehouse = build_warehouse(context)

    timeline_rows = entity_timeline(warehouse, entity="Project Atlas 1", limit=100)
    context_rows = agent_context(warehouse, entity="Project Atlas 1", limit=100)

    assert timeline_rows
    assert context_rows
    assert all("Project Atlas 16" not in row["summary"] for row in timeline_rows)
    assert all("Project Atlas 16" not in row["summary"] for row in context_rows)


def test_warehouse_entity_ids_are_collision_resistant(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    (vault / "Projects" / "Alpha Beta.md").write_text(
        "# Alpha Beta\n", encoding="utf-8"
    )
    (vault / "Projects" / "Alpha-Beta.md").write_text(
        "# Alpha-Beta\n", encoding="utf-8"
    )

    context = build_context(VaultConfig(vault_path=vault))
    warehouse = build_warehouse(context)

    entities = list_entities(warehouse, entity_type="project", limit=10)
    entity_ids = {entity["entity_id"] for entity in entities}

    assert {entity["name"] for entity in entities} == {"Alpha Beta", "Alpha-Beta"}
    assert len(entity_ids) == 2
    assert "project:alpha-beta" in entity_ids
    assert any(entity_id.startswith("project:alpha-beta:") for entity_id in entity_ids)
