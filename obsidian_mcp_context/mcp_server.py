from __future__ import annotations

import argparse
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from obsidian_mcp_context import dbt_warehouse
from obsidian_mcp_context.query import (
    get_note_context,
    list_notes,
    list_tasks,
    search_blocks,
)
from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import (
    agent_context,
    build_warehouse,
    entity_timeline,
    list_entities,
    warehouse_summary,
)


MAX_LIMIT = 200


def _bounded_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _split_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _resolve_dbt_path(duckdb_path: str | None = None) -> Path | None:
    path = dbt_warehouse.resolve_duckdb_path(duckdb_path or os.environ.get("DUCKDB_PATH"))
    if path and dbt_warehouse.is_available(path):
        return path
    return None


@lru_cache(maxsize=8)
def _load_context(
    vault_path: str,
    include_globs: str | None = None,
    exclude_globs: str | None = None,
    source_extensions: str | None = None,
):
    config = VaultConfig(
        vault_path=Path(vault_path),
        include_globs=_split_csv(include_globs, VaultConfig.include_globs),
        exclude_globs=_split_csv(exclude_globs, VaultConfig.exclude_globs),
        source_extensions=_split_csv(source_extensions, VaultConfig.source_extensions),
    )
    return build_context(config)


mcp = FastMCP(
    "obsidian-mcp-context",
    instructions=(
        "Expose AI-ready context from textual Obsidian Markdown vaults. "
        "Use these tools to list notes, search note blocks, inspect tasks, "
        "or fetch all parsed context for a source note."
    ),
)


@mcp.tool()
def list_vault_notes(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 100,
) -> list[dict[str, object]]:
    """List text notes found in the configured vault."""
    context = _load_context(vault_path)
    return list_notes(context, limit=_bounded_limit(limit))


@mcp.tool()
def search_vault_blocks(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    text: Annotated[
        str | None,
        Field(description="Optional case-insensitive text filter over block content."),
    ] = None,
    source_path: Annotated[
        str | None,
        Field(description="Optional case-insensitive filter over source path."),
    ] = None,
    heading: Annotated[
        str | None,
        Field(description="Optional case-insensitive filter over heading path."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 25,
) -> list[dict[str, object]]:
    """Search parsed note blocks with file and line provenance."""
    context = _load_context(vault_path)
    return search_blocks(
        context,
        text=text,
        source_path=source_path,
        heading=heading,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_tasks(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    checked: Annotated[
        bool | None,
        Field(description="Filter by task completion state. Omit to return both."),
    ] = None,
    text: Annotated[
        str | None,
        Field(description="Optional case-insensitive text filter over task text."),
    ] = None,
    source_path: Annotated[
        str | None,
        Field(description="Optional case-insensitive filter over source path."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
) -> list[dict[str, object]]:
    """List parsed Markdown tasks with provenance."""
    context = _load_context(vault_path)
    return list_tasks(
        context,
        checked=checked,
        text=text,
        source_path=source_path,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def get_vault_note_context(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    source_path: Annotated[
        str,
        Field(description="Vault-relative note path, such as Projects/Atlas.md."),
    ],
) -> dict[str, object]:
    """Fetch all parsed context for one vault-relative note path."""
    context = _load_context(vault_path)
    return get_note_context(context, source_path=source_path)


@mcp.tool()
def get_vault_warehouse_summary(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> dict[str, object]:
    """Summarize deterministic warehouse dimensions, facts, and marts."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if dbt_path:
        return dbt_warehouse.summary(dbt_path)
    context = _load_context(vault_path)
    warehouse = build_warehouse(context)
    return warehouse_summary(warehouse)


@mcp.tool()
def list_vault_entities(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity_type: Annotated[
        str | None,
        Field(description="Optional entity type filter, such as person or project."),
    ] = None,
    text: Annotated[
        str | None,
        Field(description="Optional case-insensitive name filter."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 100,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """List modeled entities derived from notes, wikilinks, and tags."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if dbt_path:
        return dbt_warehouse.list_entities(
            dbt_path,
            entity_type=entity_type,
            text=text,
            limit=_bounded_limit(limit),
        )
    context = _load_context(vault_path)
    warehouse = build_warehouse(context)
    return list_entities(
        warehouse,
        entity_type=entity_type,
        text=text,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def get_vault_entity_timeline(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity: Annotated[
        str,
        Field(description="Entity name to resolve deterministically in timeline rows."),
    ],
    text: Annotated[
        str | None,
        Field(description="Optional case-insensitive text filter over timeline summaries."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """Return timeline rows connected to a modeled entity."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if dbt_path:
        entities = dbt_warehouse.list_entities(dbt_path, text=entity, limit=MAX_LIMIT)
        entity_row = next(
            (row for row in entities if str(row["name"]).casefold() == entity.casefold()),
            None,
        )
        if entity_row and entity_row["entity_type"] == "project":
            return dbt_warehouse.project_context(
                dbt_path,
                project=str(entity_row["name"]),
                limit=_bounded_limit(limit),
            )
        if entity_row and entity_row["entity_type"] == "person":
            return dbt_warehouse.person_context(
                dbt_path,
                person=str(entity_row["name"]),
                limit=_bounded_limit(limit),
            )
    context = _load_context(vault_path)
    warehouse = build_warehouse(context)
    return entity_timeline(
        warehouse,
        entity=entity,
        text=text,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def search_vault_agent_context(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    text: Annotated[
        str | None,
        Field(description="Optional case-insensitive text filter over curated context."),
    ] = None,
    entity: Annotated[
        str | None,
        Field(description="Optional entity name filter."),
    ] = None,
    event_type: Annotated[
        str | None,
        Field(description="Optional mart event type, such as block or task_open."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 25,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """Search curated deterministic context rows for agent use."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if dbt_path and entity:
        entities = dbt_warehouse.list_entities(dbt_path, text=entity, limit=MAX_LIMIT)
        entity_row = next(
            (row for row in entities if str(row["name"]).casefold() == entity.casefold()),
            None,
        )
        if entity_row and entity_row["entity_type"] == "project":
            return dbt_warehouse.project_context(
                dbt_path,
                project=str(entity_row["name"]),
                limit=_bounded_limit(limit),
            )
        if entity_row and entity_row["entity_type"] == "person":
            return dbt_warehouse.person_context(
                dbt_path,
                person=str(entity_row["name"]),
                limit=_bounded_limit(limit),
            )
    if dbt_path and event_type == "open_loop":
        return dbt_warehouse.list_open_loops(
            dbt_path,
            entity=entity,
            limit=_bounded_limit(limit),
        )
    context = _load_context(vault_path)
    warehouse = build_warehouse(context)
    return agent_context(
        warehouse,
        text=text,
        entity=entity,
        event_type=event_type,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def get_vault_project_context(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    project: Annotated[str, Field(description="Project name, such as Project Atlas 1.")],
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """Return dbt mart-backed project context, including decisions, risks, and open loops."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if not dbt_path:
        return []
    return dbt_warehouse.project_context(
        dbt_path,
        project=project,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def get_vault_person_context(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    person: Annotated[str, Field(description="Person name, such as Alex Alvarez.")],
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """Return dbt mart-backed person context, including decisions, risks, and open loops."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if not dbt_path:
        return []
    return dbt_warehouse.person_context(
        dbt_path,
        person=person,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_open_loops(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity: Annotated[
        str | None,
        Field(description="Optional exact entity name filter."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """List dbt mart-backed open loops from unchecked tasks."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if not dbt_path:
        return []
    return dbt_warehouse.list_open_loops(
        dbt_path,
        entity=entity,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_decisions(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity: Annotated[
        str | None,
        Field(description="Optional exact entity name filter."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Optional decision status filter, such as active or superseded."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """List dbt mart-backed decisions with optional entity and status filters."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if not dbt_path:
        return []
    return dbt_warehouse.list_decisions(
        dbt_path,
        entity=entity,
        status=status,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_risks(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity: Annotated[
        str | None,
        Field(description="Optional exact entity name filter."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Optional risk status filter, such as open or resolved."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
    duckdb_path: Annotated[
        str | None,
        Field(
            description=(
                "Optional DuckDB warehouse path. Defaults to DUCKDB_PATH or "
                "/warehouse/obsidian.duckdb when present."
            )
        ),
    ] = None,
) -> list[dict[str, object]]:
    """List dbt mart-backed risks with optional entity and status filters."""
    dbt_path = _resolve_dbt_path(duckdb_path)
    if not dbt_path:
        return []
    return dbt_warehouse.list_risks(
        dbt_path,
        entity=entity,
        status=status,
        limit=_bounded_limit(limit),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-mcp",
        description="Run the Obsidian MCP context server.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport. Defaults to stdio for local clients.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host for HTTP transports. Defaults to the MCP library default.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for HTTP transports. Defaults to the MCP library default.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.host is not None:
        mcp.settings.host = args.host
    if args.port is not None:
        mcp.settings.port = args.port
    mcp.run(transport=args.transport)
    return 0
