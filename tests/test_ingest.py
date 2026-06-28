from pathlib import Path
from datetime import date, datetime

import duckdb

from obsidian_mcp_context.ingest import ingest_vault


def test_ingest_vault_writes_duckdb_staging_tables(tmp_path: Path):
    duckdb_path = tmp_path / "obsidian.duckdb"

    counts = ingest_vault(Path("examples/synthetic-vault"), duckdb_path)

    assert counts["base_obsidian_files"] == 120
    assert counts["base_obsidian_tasks"] == 185
    assert counts["base_obsidian_links"] == 669

    connection = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        row = connection.execute(
            """
            select
                note_type,
                title,
                source_date,
                source_created_at,
                source_observed_at,
                created_at,
                updated_at
            from base_obsidian_files
            where source_path = 'Meetings/Horizon Kickoff.md'
            """
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        "meeting",
        "Horizon Kickoff",
        date(2026, 6, 1),
        datetime(2026, 6, 1, 11, 13),
        datetime(2026, 6, 1, 14, 3),
        datetime(2026, 6, 1, 16, 39),
        datetime(2026, 6, 1, 17, 39),
    )


def test_ingest_vault_replaces_landing_tables_on_rerun(tmp_path: Path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    first_note = vault_path / "First.md"
    stale_note = vault_path / "Stale.md"
    first_note.write_text("# First\n\nInitial content.\n", encoding="utf-8")
    stale_note.write_text("# Stale\n\nThis should disappear.\n", encoding="utf-8")
    duckdb_path = tmp_path / "obsidian.duckdb"

    first_counts = ingest_vault(vault_path, duckdb_path)
    stale_note.unlink()
    second_counts = ingest_vault(vault_path, duckdb_path)

    assert first_counts["base_obsidian_files"] == 2
    assert second_counts["base_obsidian_files"] == 1

    connection = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        rows = connection.execute(
            "select source_path from base_obsidian_files order by source_path"
        ).fetchall()
    finally:
        connection.close()

    assert rows == [("First.md",)]
