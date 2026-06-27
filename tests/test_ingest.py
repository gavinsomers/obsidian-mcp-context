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
