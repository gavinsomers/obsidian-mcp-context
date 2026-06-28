from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha1
from pathlib import Path

import duckdb

from obsidian_mcp_context.domain import (
    frontmatter_value,
    note_title,
    slug,
    source_date,
)
from obsidian_mcp_context.config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    load_app_config,
    vault_config_from_app_config,
)
from obsidian_mcp_context.vault import build_context


def _executemany_if_rows(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    rows: list[tuple[object, ...]],
) -> None:
    if rows:
        connection.executemany(query, rows)


def _base_note_id(source_path: str) -> str:
    return f"note:{slug(source_path)}"


def _hashed_note_id(source_path: str) -> str:
    suffix = sha1(source_path.encode("utf-8")).hexdigest()[:8]
    return f"{_base_note_id(source_path)}:{suffix}"


def _note_ids_by_source(source_paths: list[str]) -> dict[str, str]:
    base_counts: dict[str, int] = {}
    for source_path in source_paths:
        base_id = _base_note_id(source_path)
        base_counts[base_id] = base_counts.get(base_id, 0) + 1
    return {
        source_path: (
            _hashed_note_id(source_path)
            if base_counts[_base_note_id(source_path)] > 1
            else _base_note_id(source_path)
        )
        for source_path in source_paths
    }


def _create_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        create or replace table base_obsidian_files (
            note_id varchar,
            source_path varchar,
            absolute_path varchar,
            note_type varchar,
            title varchar,
            source_date date,
            source_created_at timestamp,
            source_observed_at timestamp,
            created_at timestamp,
            updated_at timestamp
        )
        """
    )
    connection.execute(
        """
        create or replace table base_obsidian_blocks (
            source_path varchar,
            block_id varchar,
            block_hash varchar,
            heading varchar,
            heading_path varchar,
            heading_level integer,
            start_line integer,
            end_line integer,
            text varchar
        )
        """
    )
    connection.execute(
        """
        create or replace table base_obsidian_tasks (
            source_path varchar,
            block_id varchar,
            task_id varchar,
            task_text varchar,
            checked boolean,
            line_number integer,
            heading varchar,
            heading_path varchar,
            block_hash varchar
        )
        """
    )
    connection.execute(
        """
        create or replace table base_obsidian_links (
            source_path varchar,
            block_id varchar,
            link_target varchar,
            link_text varchar,
            line_number integer
        )
        """
    )
    connection.execute(
        """
        create or replace table base_obsidian_tags (
            source_path varchar,
            block_id varchar,
            tag varchar,
            line_number integer
        )
        """
    )
    connection.execute(
        """
        create or replace table base_obsidian_lines (
            source_path varchar,
            block_id varchar,
            line_number integer,
            heading varchar,
            heading_path varchar,
            text varchar
        )
        """
    )
    connection.execute(
        """
        create or replace table base_obsidian_config_non_entity_note_types (
            note_type varchar
        )
        """
    )


def ingest_vault(
    vault_path: Path,
    duckdb_path: Path,
    config_path: Path | None = None,
) -> dict[str, int]:
    app_config = load_app_config(config_path) if config_path else AppConfig()
    context = build_context(vault_config_from_app_config(vault_path, app_config))
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    first_block_text_by_source = {
        block.source_path: block.text for block in reversed(context.blocks)
    }
    note_ids_by_source = _note_ids_by_source(
        [source_file.source_path for source_file in context.files]
    )

    connection = duckdb.connect(str(duckdb_path))
    try:
        _create_tables(connection)
        files = []
        for source_file in context.files:
            first_block_text = first_block_text_by_source.get(source_file.source_path)
            files.append(
                (
                    note_ids_by_source[source_file.source_path],
                    source_file.source_path,
                    str(source_file.absolute_path),
                    source_file.note_type,
                    note_title(source_file.source_path),
                    source_date(source_file.source_path, first_block_text),
                    frontmatter_value(first_block_text, "source_created_at"),
                    frontmatter_value(first_block_text, "source_observed_at"),
                    frontmatter_value(first_block_text, "created_at"),
                    frontmatter_value(first_block_text, "updated_at"),
                )
            )
        _executemany_if_rows(
            connection,
            "insert into base_obsidian_files values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            files,
        )
        _executemany_if_rows(
            connection,
            "insert into base_obsidian_blocks values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(asdict(block).values()) for block in context.blocks],
        )
        _executemany_if_rows(
            connection,
            "insert into base_obsidian_tasks values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(asdict(task).values()) for task in context.tasks],
        )
        _executemany_if_rows(
            connection,
            "insert into base_obsidian_links values (?, ?, ?, ?, ?)",
            [tuple(asdict(link).values()) for link in context.links],
        )
        _executemany_if_rows(
            connection,
            "insert into base_obsidian_tags values (?, ?, ?, ?)",
            [tuple(asdict(tag).values()) for tag in context.tags],
        )
        _executemany_if_rows(
            connection,
            "insert into base_obsidian_lines values (?, ?, ?, ?, ?, ?)",
            [tuple(asdict(line).values()) for line in context.lines],
        )
        _executemany_if_rows(
            connection,
            "insert into base_obsidian_config_non_entity_note_types values (?)",
            [(note_type,) for note_type in app_config.non_entity_note_types],
        )
        counts = {
            table: connection.execute(f"select count(*) from {table}").fetchone()[0]
            for table in (
                "base_obsidian_files",
                "base_obsidian_blocks",
                "base_obsidian_tasks",
                "base_obsidian_links",
                "base_obsidian_tags",
                "base_obsidian_lines",
                "base_obsidian_config_non_entity_note_types",
            )
        }
    finally:
        connection.close()
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-ingest",
        description="Ingest parsed Obsidian vault context into DuckDB landing tables.",
    )
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault.")
    parser.add_argument(
        "--duckdb",
        required=True,
        help="Path to the DuckDB database file to create or replace landing tables in.",
    )
    parser.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path for local scan and entity settings.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    counts = ingest_vault(
        Path(args.vault),
        Path(args.duckdb),
        config_path=Path(args.config) if args.config else DEFAULT_CONFIG_PATH,
    )
    for table, count in counts.items():
        print(f"{table}: {count}")
    return 0
