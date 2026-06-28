from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

import duckdb

from obsidian_mcp_context import dbt_warehouse
from obsidian_mcp_context.security import validate_vault_path


DEFAULT_WRITER_DUCKDB_PATH = Path("/warehouse/obsidian.duckdb")
DEFAULT_READ_DUCKDB_PATH = Path("/warehouse/obsidian-read.duckdb")

STATUS_TABLES = (
    "base_obsidian_files",
    "dim_notes",
    "dim_entities",
    "fact_tasks",
    "fact_mentions",
    "mart_open_loops",
    "mart_project_context",
    "mart_person_context",
)


def _iso_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _path_status(path: Path) -> dict[str, object]:
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "modified_at": _iso_mtime(path),
        "size_bytes": path.stat().st_size if exists else None,
    }


def _resolve_existing_or_default(value: str | Path | None, default: Path) -> Path:
    if value:
        return Path(value).expanduser()
    return default


def _table_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        with dbt_warehouse.connect(path) as connection:
            rows = connection.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'main'
                """
            ).fetchall()
    except (duckdb.Error, OSError):
        return set()
    return {str(row[0]) for row in rows}


def _row_counts(path: Path, tables: tuple[str, ...] = STATUS_TABLES) -> dict[str, int | None]:
    available_tables = _table_names(path)
    if not available_tables:
        return {table: None for table in tables}
    counts: dict[str, int | None] = {}
    try:
        with dbt_warehouse.connect(path) as connection:
            for table in tables:
                if table not in available_tables:
                    counts[table] = None
                    continue
                counts[table] = int(
                    connection.execute(f"select count(*) from {table}").fetchone()[0]
                )
    except (duckdb.Error, OSError):
        return {table: None for table in tables}
    return counts


def warehouse_status(
    vault_path: str | Path,
    active_duckdb_path: str | Path | None = None,
    writer_duckdb_path: str | Path | None = None,
    read_duckdb_path: str | Path | None = None,
) -> dict[str, object]:
    """Return file and warehouse status for the local web/MCP pipeline."""
    vault = validate_vault_path(vault_path)
    writer_path = _resolve_existing_or_default(
        writer_duckdb_path or os.environ.get("WRITER_DUCKDB_PATH"),
        DEFAULT_WRITER_DUCKDB_PATH,
    )
    read_path = _resolve_existing_or_default(
        read_duckdb_path or os.environ.get("READ_DUCKDB_PATH"),
        DEFAULT_READ_DUCKDB_PATH,
    )
    active_path = _resolve_existing_or_default(
        active_duckdb_path or os.environ.get("DUCKDB_PATH"),
        read_path if read_path.exists() else writer_path,
    )
    table_names = _table_names(active_path)
    read_modified_at = _iso_mtime(read_path)
    writer_modified_at = _iso_mtime(writer_path)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault": {
            "path": str(vault),
            "exists": vault.exists(),
            "markdown_file_count": (
                sum(1 for path in vault.rglob("*.md") if path.is_file())
                if vault.exists()
                else 0
            ),
        },
        "warehouse": {
            "active_reader": {
                **_path_status(active_path),
                "available": dbt_warehouse.is_available(active_path),
                "is_stable_snapshot": active_path == read_path,
            },
            "writer": {
                **_path_status(writer_path),
                "available": dbt_warehouse.is_available(writer_path),
            },
            "read_snapshot": {
                **_path_status(read_path),
                "available": dbt_warehouse.is_available(read_path),
            },
            "reading_from_stable_snapshot": active_path == read_path and read_path.exists(),
            "snapshot_freshness": {
                "writer_modified_at": writer_modified_at,
                "read_snapshot_modified_at": read_modified_at,
                "read_snapshot_is_at_least_as_new_as_writer": (
                    None
                    if not writer_path.exists() or not read_path.exists()
                    else read_path.stat().st_mtime >= writer_path.stat().st_mtime
                ),
            },
            "row_counts": _row_counts(active_path),
            "missing_required_marts": sorted(dbt_warehouse.REQUIRED_MARTS - table_names),
            "missing_status_tables": [
                table for table in STATUS_TABLES if table not in table_names
            ],
        },
    }
