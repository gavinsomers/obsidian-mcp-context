from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from obsidian_mcp_context.config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    load_app_config,
    vault_config_from_app_config,
)
from obsidian_mcp_context.domain import frontmatter_value, note_title, source_date
from obsidian_mcp_context.vault import build_context


LANDING_TABLES = (
    "base_obsidian_files",
    "base_obsidian_blocks",
    "base_obsidian_tasks",
    "base_obsidian_links",
    "base_obsidian_tags",
    "base_obsidian_lines",
    "base_obsidian_config_non_entity_note_types",
    "base_obsidian_ingest_profile",
)
SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_schema(schema: str) -> str:
    if not SCHEMA_RE.fullmatch(schema):
        raise ValueError(f"Invalid Postgres schema name: {schema}")
    return schema


def _executemany_if_rows(cursor, query: str, rows: list[tuple[object, ...]]) -> None:
    if rows:
        cursor.executemany(query, rows)


def _note_ids_by_source(source_paths: list[str]) -> dict[str, str]:
    return {
        source_path: f"note_{index:06d}"
        for index, source_path in enumerate(sorted(source_paths), start=1)
    }


def _create_schema_and_tables(cursor, schema: str) -> None:
    schema = _validate_schema(schema)
    cursor.execute(f"create schema if not exists {schema}")
    for table in LANDING_TABLES:
        cursor.execute(f"drop table if exists {schema}.{table} cascade")
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_files (
            note_id text,
            source_path text,
            absolute_path text,
            note_type text,
            title text,
            source_date date,
            source_created_at timestamp,
            source_observed_at timestamp,
            created_at timestamp,
            updated_at timestamp
        )
        """
    )
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_blocks (
            source_path text,
            block_id text,
            block_hash text,
            heading text,
            heading_path text,
            heading_level integer,
            start_line integer,
            end_line integer,
            text text
        )
        """
    )
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_tasks (
            source_path text,
            block_id text,
            task_id text,
            task_text text,
            checked boolean,
            line_number integer,
            heading text,
            heading_path text,
            block_hash text
        )
        """
    )
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_links (
            source_path text,
            block_id text,
            link_target text,
            link_text text,
            line_number integer
        )
        """
    )
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_tags (
            source_path text,
            block_id text,
            tag text,
            line_number integer
        )
        """
    )
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_lines (
            source_path text,
            block_id text,
            line_number integer,
            heading text,
            heading_path text,
            text text
        )
        """
    )
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_config_non_entity_note_types (
            note_type text
        )
        """
    )
    cursor.execute(
        f"""
        create table {schema}.base_obsidian_ingest_profile (
            profile_loaded boolean,
            config_loaded boolean,
            profile_ref text,
            config_ref text,
            include_globs jsonb,
            exclude_globs jsonb,
            source_extensions jsonb,
            folder_note_types jsonb,
            non_entity_note_types jsonb,
            note_type_counts jsonb,
            source_file_count integer,
            profile_fingerprint text
        )
        """
    )


def _profile_ref(path: Path | None) -> str:
    if not path:
        return ""
    if not path.is_absolute():
        return path.as_posix()
    return f"<redacted:{path.name}>"


def _profile_fingerprint(values: dict[str, object]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def build_ingest_payload(
    vault_path: Path,
    *,
    config_path: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, object]:
    app_config = (
        load_app_config(config_path, profile_path=profile_path)
        if config_path or profile_path or os.environ.get("OBSIDIAN_MCP_VAULT_PROFILE")
        else AppConfig()
    )
    context = build_context(vault_config_from_app_config(vault_path, app_config))
    first_block_text_by_source = {
        block.source_path: block.text for block in reversed(context.blocks)
    }
    note_ids_by_source = _note_ids_by_source(
        [source_file.source_path for source_file in context.files]
    )
    files = []
    note_type_counts: dict[str, int] = {}
    for source_file in context.files:
        first_block_text = first_block_text_by_source.get(source_file.source_path)
        note_type_counts[source_file.note_type] = (
            note_type_counts.get(source_file.note_type, 0) + 1
        )
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

    profile_fingerprint_values = {
        "include_globs": app_config.include_globs,
        "exclude_globs": app_config.exclude_globs,
        "source_extensions": app_config.source_extensions,
        "folder_note_types": app_config.folder_note_types,
        "non_entity_note_types": app_config.non_entity_note_types,
    }
    profile_row = (
        app_config.profile_path is not None,
        app_config.loaded,
        _profile_ref(app_config.profile_path),
        _profile_ref(app_config.config_path) if config_path else "",
        _json(list(app_config.include_globs)),
        _json(list(app_config.exclude_globs)),
        _json(list(app_config.source_extensions)),
        _json(app_config.folder_note_types),
        _json(list(app_config.non_entity_note_types)),
        _json(note_type_counts),
        len(context.files),
        _profile_fingerprint(profile_fingerprint_values),
    )
    return {
        "app_config": app_config,
        "context": context,
        "files": files,
        "profile_row": profile_row,
    }


def ingest_vault_postgres(
    vault_path: Path,
    connection_string: str,
    *,
    schema: str = "raw",
    config_path: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, int]:
    import psycopg

    payload = build_ingest_payload(
        vault_path,
        config_path=config_path,
        profile_path=profile_path,
    )
    app_config = payload["app_config"]
    context = payload["context"]
    files = payload["files"]
    profile_row = payload["profile_row"]

    with psycopg.connect(connection_string) as connection:
        with connection.cursor() as cursor:
            schema = _validate_schema(schema)
            _create_schema_and_tables(cursor, schema)
            _executemany_if_rows(
                cursor,
                f"insert into {schema}.base_obsidian_files values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                files,
            )
            _executemany_if_rows(
                cursor,
                f"insert into {schema}.base_obsidian_blocks values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [tuple(asdict(block).values()) for block in context.blocks],
            )
            _executemany_if_rows(
                cursor,
                f"insert into {schema}.base_obsidian_tasks values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [tuple(asdict(task).values()) for task in context.tasks],
            )
            _executemany_if_rows(
                cursor,
                f"insert into {schema}.base_obsidian_links values (%s, %s, %s, %s, %s)",
                [tuple(asdict(link).values()) for link in context.links],
            )
            _executemany_if_rows(
                cursor,
                f"insert into {schema}.base_obsidian_tags values (%s, %s, %s, %s)",
                [tuple(asdict(tag).values()) for tag in context.tags],
            )
            _executemany_if_rows(
                cursor,
                f"insert into {schema}.base_obsidian_lines values (%s, %s, %s, %s, %s, %s)",
                [tuple(asdict(line).values()) for line in context.lines],
            )
            _executemany_if_rows(
                cursor,
                f"insert into {schema}.base_obsidian_config_non_entity_note_types values (%s)",
                [(note_type,) for note_type in app_config.non_entity_note_types],
            )
            cursor.execute(
                f"insert into {schema}.base_obsidian_ingest_profile values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)",
                profile_row,
            )
            counts = {}
            for table in LANDING_TABLES:
                cursor.execute(f"select count(*) from {schema}.{table}")
                counts[table] = int(cursor.fetchone()[0])
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-ingest-postgres",
        description="Rebuild Postgres landing tables from a full parse of an Obsidian vault.",
    )
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault.")
    parser.add_argument(
        "--connection",
        default=os.environ.get("POSTGRES_DSN"),
        help="Postgres connection string. Defaults to POSTGRES_DSN.",
    )
    parser.add_argument("--schema", default=os.environ.get("POSTGRES_RAW_SCHEMA", "raw"))
    parser.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path for local scan and entity settings.",
    )
    parser.add_argument(
        "--vault-profile",
        help=(
            "Optional vault profile TOML path or checked-in profile name from "
            "examples/vault-profiles. Loaded before --config."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.connection:
        parser.error("--connection or POSTGRES_DSN is required")
    counts = ingest_vault_postgres(
        Path(args.vault),
        args.connection,
        schema=args.schema,
        config_path=Path(args.config) if args.config else DEFAULT_CONFIG_PATH,
        profile_path=Path(args.vault_profile) if args.vault_profile else None,
    )
    for table, count in counts.items():
        print(f"{table}: {count}")
    return 0
