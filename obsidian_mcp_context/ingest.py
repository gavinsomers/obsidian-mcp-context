from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import duckdb

from obsidian_mcp_context.domain import (
    frontmatter_value,
    note_title,
    note_type,
    slug,
    source_date,
)
from obsidian_mcp_context.vault import VaultConfig, build_context


def _executemany_if_rows(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    rows: list[tuple[object, ...]],
) -> None:
    if rows:
        connection.executemany(query, rows)


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


def ingest_vault(vault_path: Path, duckdb_path: Path) -> dict[str, int]:
    context = build_context(VaultConfig(vault_path=vault_path))
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    first_block_text_by_source = {
        block.source_path: block.text for block in reversed(context.blocks)
    }

    connection = duckdb.connect(str(duckdb_path))
    try:
        _create_tables(connection)
        files = []
        for source_file in context.files:
            first_block_text = first_block_text_by_source.get(source_file.source_path)
            files.append(
                (
                    f"note:{slug(source_file.source_path)}",
                    source_file.source_path,
                    str(source_file.absolute_path),
                    note_type(source_file.source_path),
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
        counts = {
            table: connection.execute(f"select count(*) from {table}").fetchone()[0]
            for table in (
                "base_obsidian_files",
                "base_obsidian_blocks",
                "base_obsidian_tasks",
                "base_obsidian_links",
                "base_obsidian_tags",
                "base_obsidian_lines",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    counts = ingest_vault(Path(args.vault), Path(args.duckdb))
    for table, count in counts.items():
        print(f"{table}: {count}")
    return 0
