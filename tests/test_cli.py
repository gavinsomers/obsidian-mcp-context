from __future__ import annotations

import json
from pathlib import Path

import duckdb

from obsidian_mcp_context.cli import main


def _write_cli_dbt_warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            create table dim_notes (
              note_id text,
              source_path text,
              note_type text,
              title text,
              source_date date,
              source_created_at timestamp,
              source_observed_at timestamp,
              created_at timestamp,
              updated_at timestamp
            );
            create table dim_entities (
              entity_id text,
              entity_type text,
              name text,
              source_path text,
              canonical_note_id text
            );
            create table dim_entity_types (entity_type text);
            create table dim_people (person_id text);
            create table dim_companies (company_id text);
            create table dim_projects (project_id text);
            create table fact_blocks (block_id text);
            create table fact_tasks (task_id text);
            create table fact_links (link_id text);
            create table fact_tags (tag_id text);
            create table fact_mentions (mention_id text);
            create table fact_entity_relationships (relationship_id text);
            create table fact_entity_states (state_id text);
            create table fact_entity_events (event_id text);
            create table fact_decisions (decision_id text);
            create table fact_risks (risk_id text);
            create table mart_timeline (timeline_id text);
            create table mart_entity_context (entity_context_id text);
            create table mart_entity_open_loops (entity_open_loop_id text);
            create table mart_open_loops (open_loop_id text);
            create table mart_person_context (person_context_id text);
            create table mart_project_context (project_context_id text);
            """
        )
        connection.execute(
            """
            insert into dim_notes values (
              'note:atlas',
              'Projects/Atlas.md',
              'project',
              'Project Atlas',
              date '2026-06-28',
              timestamp '2026-06-28 09:00:00',
              timestamp '2026-06-28 09:05:00',
              timestamp '2026-06-28 09:10:00',
              timestamp '2026-06-28 09:15:00'
            )
            """
        )
        connection.execute(
            """
            insert into dim_entities values (
              'project:atlas',
              'project',
              'Project Atlas',
              'Projects/Atlas.md',
              'note:atlas'
            )
            """
        )
    finally:
        connection.close()


def test_cli_entities_prefers_duckdb_marts(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Ignored.md").write_text("# Ignored\n", encoding="utf-8")
    duckdb_path = tmp_path / "warehouse.duckdb"
    _write_cli_dbt_warehouse(duckdb_path)

    result = main(
        [
            "--vault",
            str(vault),
            "entities",
            "--duckdb",
            str(duckdb_path),
            "--entity-type",
            "project",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    assert json.loads(captured.out)[0]["name"] == "Project Atlas"


def test_cli_modeled_command_warns_on_direct_parse_fallback(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Project Atlas.md").write_text("# Project Atlas\n", encoding="utf-8")

    result = main(["--vault", str(vault), "entities"])

    captured = capsys.readouterr()
    assert result == 0
    assert "falling back to direct parser diagnostics" in captured.err
