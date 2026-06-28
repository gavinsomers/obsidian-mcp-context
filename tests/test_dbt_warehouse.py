from pathlib import Path
import os
import subprocess
import sys

import duckdb

from obsidian_mcp_context import dbt_warehouse
from obsidian_mcp_context.ingest import ingest_vault
from obsidian_mcp_context.web_ui import answer_question


def _write_minimal_dbt_warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            create table dim_notes (note_id text, title text);
            create table dim_entities (
              entity_id text,
              entity_type text,
              name text,
              source_path text,
              canonical_note_id text
            );
            create table dim_entity_types (
              entity_type text,
              display_name text,
              description text,
              source_strategy text,
              is_stateful boolean,
              is_actor boolean,
              is_container boolean
            );
            create table fact_blocks (block_id text);
            create table fact_tasks (task_id text);
            create table fact_links (link_id text);
            create table fact_tags (tag_id text);
            create table fact_mentions (mention_id text);
            create table fact_entity_relationships (
              relationship_id text,
              source_entity_id text,
              source_entity_type text,
              source_entity_name text,
              target_entity_id text,
              target_entity_type text,
              target_entity_name text,
              relationship_type text,
              source_path text,
              line_number integer,
              confidence double,
              evidence_text text
            );
            create table fact_entity_states (
              state_id text,
              entity_id text,
              entity_type text,
              entity_name text,
              state_type text,
              state_value text,
              state_date date,
              severity text,
              owner_entity_id text,
              owner_entity_name text,
              source_path text,
              title text,
              summary text,
              related_entities text
            );
            create table fact_entity_events (
              event_id text,
              entity_id text,
              entity_type text,
              entity_name text,
              event_type text,
              event_date date,
              source_path text,
              start_line integer,
              title text,
              summary text,
              related_entities text
            );
            create table dim_people (person_id text, name text);
            create table dim_companies (company_id text, name text);
            create table dim_projects (project_id text, name text);
            create table mart_timeline (
              timeline_id text,
              event_date date,
              event_type text,
              source_path text,
              start_line integer,
              title text,
              summary text,
              related_entities text
            );
            create table mart_project_context (
              project_context_id text,
              project_id text,
              project_name text,
              timeline_id text,
              event_date date,
              event_type text,
              source_path text,
              start_line integer,
              title text,
              summary text,
              related_entities text
            );
            create table mart_person_context (
              person_context_id text,
              person_id text,
              person_name text,
              timeline_id text,
              event_date date,
              event_type text,
              source_path text,
              start_line integer,
              title text,
              summary text,
              related_entities text
            );
            create table fact_decisions (
              decision_id text,
              decision_date date,
              decision_status text,
              source_path text,
              title text,
              summary text,
              projects text,
              companies text,
              people text
            );
            create table fact_risks (
              risk_id text,
              risk_date date,
              risk_status text,
              source_path text,
              title text,
              summary text,
              projects text,
              companies text,
              people text
            );
            create table mart_open_loops (
              open_loop_id text,
              source_date date,
              source_path text,
              line_number integer,
              heading_path text,
              source_title text,
              task_text text,
              related_entities text,
              people text,
              companies text,
              projects text,
              risks text
            );
            create table mart_entity_open_loops (
              entity_open_loop_id text,
              entity_id text,
              entity_type text,
              entity_name text,
              open_loop_id text,
              task_id text,
              source_date date,
              source_path text,
              line_number integer,
              heading_path text,
              source_title text,
              task_text text,
              related_entities text,
              owner_entity_id text,
              owner_entity_name text
            );
            create table mart_entity_context (
              entity_context_id text,
              entity_id text,
              entity_type text,
              entity_name text,
              event_id text,
              event_date date,
              event_type text,
              source_path text,
              start_line integer,
              title text,
              summary text,
              related_entities text,
              rank_score integer
            );
            """
        )
        connection.execute(
            """
            insert into dim_entities values
              ('project:atlas', 'project', 'Project Atlas', 'Projects/Atlas.md', 'note:atlas'),
              ('project:atlas-16', 'project', 'Project Atlas 16', 'Projects/Atlas 16.md', 'note:atlas-16'),
              ('person:morgan', 'person', 'Morgan Lee', 'People/Morgan Lee.md', 'note:morgan');
            insert into dim_entity_types values
              ('project', 'Project', 'A project.', 'note_or_link', true, false, true),
              ('person', 'Person', 'A person.', 'note_or_link', true, true, false);
            insert into dim_projects values
              ('project:atlas', 'Project Atlas'),
              ('project:atlas-16', 'Project Atlas 16');
            insert into dim_people values ('person:morgan', 'Morgan Lee');
            insert into dim_companies values ('company:northstar', 'Northstar Labs');
            insert into mart_project_context values
              (
                'pc1',
                'project:atlas',
                'Project Atlas',
                'tl1',
                date '2026-05-18',
                'block',
                'Daily/2026-05-18.md',
                10,
                'Daily > Notes',
                'Reviewed [[Project Atlas]] with [[Morgan Lee]].',
                'Project Atlas, Morgan Lee'
              ),
              (
                'pc2',
                'project:atlas-16',
                'Project Atlas 16',
                'tl2',
                date '2026-06-18',
                'block',
                'Daily/2026-06-18.md',
                11,
                'Daily > Notes',
                'Reviewed [[Project Atlas 16]].',
                'Project Atlas 16'
              );
            insert into fact_decisions values
              (
                'decision:1',
                date '2026-05-19',
                'active',
                'Decisions/Atlas Scope.md',
                'Atlas Scope',
                'Proceed with [[Project Atlas]].',
                'Project Atlas',
                'Northstar Labs',
                'Morgan Lee'
              );
            insert into fact_risks values
              (
                'risk:1',
                date '2026-05-20',
                'open',
                'Risks/Atlas Risk.md',
                'Atlas Risk',
                'Blocked data access for [[Project Atlas]].',
                'Project Atlas',
                'Northstar Labs',
                ''
              );
            insert into fact_entity_relationships values
              (
                'relationship:1',
                'project:atlas',
                'project',
                'Project Atlas',
                'person:morgan',
                'person',
                'Morgan Lee',
                'co_mentioned_with',
                'Daily/2026-05-18.md',
                10,
                0.7,
                'Reviewed [[Project Atlas]] with [[Morgan Lee]].'
              );
            insert into fact_entity_states values
              (
                'state:risk:1',
                'project:atlas',
                'project',
                'Project Atlas',
                'risk_status',
                'open',
                date '2026-05-20',
                'medium',
                'person:morgan',
                'Morgan Lee',
                'Risks/Atlas Risk.md',
                'Atlas Risk',
                'Blocked data access for Project Atlas.',
                'Project Atlas, Morgan Lee'
              );
            insert into fact_entity_events values
              (
                'event:1',
                'project:atlas',
                'project',
                'Project Atlas',
                'block',
                date '2026-05-18',
                'Daily/2026-05-18.md',
                10,
                'Daily > Notes',
                'Reviewed [[Project Atlas]] with [[Morgan Lee]].',
                'Project Atlas, Morgan Lee'
              );
            insert into mart_open_loops values
              (
                'task:1',
                date '2026-05-21',
                'Daily/2026-05-21.md',
                7,
                'Daily > Tasks',
                '2026-05-21',
                'Follow up on [[Project Atlas]].',
                'Project Atlas, Morgan Lee',
                'Morgan Lee',
                'Northstar Labs',
                'Project Atlas',
                ''
              );
            insert into mart_entity_open_loops values
              (
                'entity_open_loop:task:1:project:atlas',
                'project:atlas',
                'project',
                'Project Atlas',
                'task:1',
                'task:1',
                date '2026-05-21',
                'Daily/2026-05-21.md',
                7,
                'Daily > Tasks',
                '2026-05-21',
                'Follow up on [[Project Atlas]].',
                'Project Atlas, Morgan Lee',
                'person:morgan',
                'Morgan Lee'
              );
            insert into mart_entity_context values
              (
                'context:event:1',
                'project:atlas',
                'project',
                'Project Atlas',
                'event:1',
                date '2026-05-18',
                'block',
                'Daily/2026-05-18.md',
                10,
                'Daily > Notes',
                'Reviewed [[Project Atlas]] with [[Morgan Lee]].',
                'Project Atlas, Morgan Lee',
                0
              );
            """
        )
    finally:
        connection.close()


def test_dbt_warehouse_project_context_combines_marts(tmp_path: Path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    _write_minimal_dbt_warehouse(duckdb_path)

    rows = dbt_warehouse.project_context(duckdb_path, "Project Atlas", limit=20)

    event_types = {row["event_type"] for row in rows}
    assert dbt_warehouse.is_available(duckdb_path)
    assert {"block", "decision_active", "risk_open", "open_loop"}.issubset(event_types)
    assert all("Project Atlas 16" not in row["summary"] for row in rows)
    assert rows[0]["event_date"] == "2026-05-18"


def test_web_ui_prefers_dbt_warehouse_for_project_context(tmp_path: Path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    _write_minimal_dbt_warehouse(duckdb_path)

    answer = answer_question(
        vault_path,
        "Show me the timeline for Project Atlas with related decisions risks and open tasks",
        duckdb_path=duckdb_path,
    )

    assert answer["warehouse"] == "dbt"
    assert answer["mode"] == "project_context"
    assert answer["entity"] == "Project Atlas"
    assert {row["event_type"] for row in answer["results"]} >= {
        "decision_active",
        "risk_open",
        "open_loop",
    }


def test_web_ui_prefers_longest_dbt_entity_match(tmp_path: Path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    _write_minimal_dbt_warehouse(duckdb_path)

    answer = answer_question(
        vault_path,
        "Show me the timeline for Project Atlas 16",
        duckdb_path=duckdb_path,
    )

    assert answer["mode"] == "project_context"
    assert answer["entity"] == "Project Atlas 16"
    assert answer["results"][0]["summary"] == "Reviewed [[Project Atlas 16]]."


def test_dbt_warehouse_generic_entity_queries(tmp_path: Path):
    duckdb_path = tmp_path / "warehouse.duckdb"
    _write_minimal_dbt_warehouse(duckdb_path)

    entity_types = dbt_warehouse.list_entity_types(duckdb_path)
    context = dbt_warehouse.entity_context(
        duckdb_path,
        entity_type="project",
        entity="Project Atlas",
    )
    relationships = dbt_warehouse.list_entity_relationships(
        duckdb_path,
        entity_type="project",
        entity="Project Atlas",
    )
    states = dbt_warehouse.list_entity_states(
        duckdb_path,
        entity_type="project",
        entity="Project Atlas",
        status="open",
    )
    open_loops = dbt_warehouse.list_entity_open_loops(
        duckdb_path,
        entity_type="project",
        entity="Project Atlas",
    )

    assert {row["entity_type"] for row in entity_types} >= {"project", "person"}
    assert context[0]["entity_name"] == "Project Atlas"
    assert relationships[0]["target_entity_name"] == "Morgan Lee"
    assert states[0]["state_value"] == "open"
    assert open_loops[0]["summary"] == "Follow up on [[Project Atlas]]."


def test_dbt_pipeline_materializes_custom_entity_types(tmp_path: Path):
    vault_path = tmp_path / "vault"
    duckdb_path = tmp_path / "obsidian.duckdb"
    (vault_path / "Clients").mkdir(parents=True)
    (vault_path / "Assets").mkdir()
    (vault_path / "Initiatives").mkdir()
    (vault_path / "Daily").mkdir()
    (vault_path / "Clients" / "Acme Renewal.md").write_text(
        """---
source_created_at: 2026-06-01T09:00:00
source_observed_at: 2026-06-01T09:05:00
created_at: 2026-06-01T09:10:00
updated_at: 2026-06-01T09:20:00
---
# Acme Renewal

Client depends on [[Revenue Dashboard]] and [[Data Trust]].
""",
        encoding="utf-8",
    )
    (vault_path / "Assets" / "Revenue Dashboard.md").write_text(
        """---
source_created_at: 2026-06-02T09:00:00
source_observed_at: 2026-06-02T09:05:00
created_at: 2026-06-02T09:10:00
updated_at: 2026-06-02T09:20:00
---
# Revenue Dashboard

Dashboard supports [[Acme Renewal]].
""",
        encoding="utf-8",
    )
    (vault_path / "Initiatives" / "Data Trust.md").write_text(
        """---
source_created_at: 2026-06-03T09:00:00
source_observed_at: 2026-06-03T09:05:00
created_at: 2026-06-03T09:10:00
updated_at: 2026-06-03T09:20:00
---
# Data Trust

Initiative includes [[Acme Renewal]].
""",
        encoding="utf-8",
    )
    (vault_path / "Daily" / "2026-06-28.md").write_text(
        """---
source_created_at: 2026-06-28T09:00:00
source_observed_at: 2026-06-28T09:05:00
created_at: 2026-06-28T09:10:00
updated_at: 2026-06-28T09:20:00
---
# Daily

- [ ] Review [[Acme Renewal]] rollout with [[Revenue Dashboard]] owner.
""",
        encoding="utf-8",
    )

    ingest_vault(vault_path, duckdb_path)
    env = os.environ | {"DUCKDB_PATH": str(duckdb_path)}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dbt.cli.main",
            "run",
            "--profiles-dir",
            "dbt",
            "--project-dir",
            ".",
            "--quiet",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
    )

    entities = dbt_warehouse.list_entities(duckdb_path, limit=100)
    entity_types = dbt_warehouse.list_entity_types(duckdb_path, limit=100)
    context = dbt_warehouse.entity_context(
        duckdb_path,
        entity_type="client",
        entity="Acme Renewal",
        limit=50,
    )
    relationships = dbt_warehouse.list_entity_relationships(
        duckdb_path,
        entity_type="client",
        entity="Acme Renewal",
        limit=50,
    )
    open_loops = dbt_warehouse.list_entity_open_loops(
        duckdb_path,
        entity_type="client",
        entity="Acme Renewal",
        limit=50,
    )

    assert {(row["entity_type"], row["name"]) for row in entities} >= {
        ("client", "Acme Renewal"),
        ("asset", "Revenue Dashboard"),
        ("initiative", "Data Trust"),
    }
    assert {row["entity_type"] for row in entity_types} >= {
        "client",
        "asset",
        "initiative",
    }
    assert context
    assert any(row["event_type"] == "open_loop" for row in context)
    assert any(row["target_entity_name"] == "Revenue Dashboard" for row in relationships)
    assert open_loops[0]["summary"].startswith("Review [[Acme Renewal]]")
