from pathlib import Path

import duckdb

from obsidian_mcp_context import dbt_warehouse
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
            create table fact_blocks (block_id text);
            create table fact_tasks (task_id text);
            create table fact_links (link_id text);
            create table fact_tags (tag_id text);
            create table fact_mentions (mention_id text);
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
            """
        )
        connection.execute(
            """
            insert into dim_entities values
              ('project:atlas', 'project', 'Project Atlas', 'Projects/Atlas.md', 'note:atlas'),
              ('project:atlas-16', 'project', 'Project Atlas 16', 'Projects/Atlas 16.md', 'note:atlas-16'),
              ('person:morgan', 'person', 'Morgan Lee', 'People/Morgan Lee.md', 'note:morgan');
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
