from __future__ import annotations

import argparse
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from obsidian_mcp_context.security import validate_vault_path
from obsidian_mcp_context.services import default_context_service
from obsidian_mcp_context.vault import VaultConfig


MAX_LIMIT = 200


def _bounded_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _load_context(
    vault_path: str,
    include_globs: str | None = None,
    exclude_globs: str | None = None,
    source_extensions: str | None = None,
):
    return default_context_service.context(
        vault_path,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
        source_extensions=source_extensions,
    )


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
    return default_context_service.list_notes(vault_path, limit=_bounded_limit(limit))


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
    return default_context_service.search_blocks(
        vault_path,
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
    return default_context_service.list_tasks(
        vault_path,
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
    return default_context_service.note_context(vault_path, source_path=source_path)


@mcp.tool()
def get_vault_warehouse_summary(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
) -> dict[str, object]:
    """Summarize deterministic warehouse dimensions, facts, and marts."""
    return default_context_service.warehouse_summary(vault_path, warehouse_path=None)


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
) -> list[dict[str, object]]:
    """List modeled entities derived from notes, wikilinks, and tags."""
    return default_context_service.list_entities(
        vault_path,
        entity_type=entity_type,
        text=text,
        limit=_bounded_limit(limit),
        warehouse_path=None,
    )


@mcp.tool()
def list_vault_entity_types(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 100,
) -> list[dict[str, object]]:
    """List entity types observed in the dbt entity registry."""
    validate_vault_path(vault_path)
    return default_context_service.entity_types(
        None,
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
) -> list[dict[str, object]]:
    """Return timeline rows connected to a modeled entity."""
    return default_context_service.entity_timeline(
        vault_path,
        entity=entity,
        text=text,
        limit=_bounded_limit(limit),
        warehouse_path=None,
    )


@mcp.tool()
def get_vault_entity_context(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity_type: Annotated[
        str,
        Field(description="Entity type, such as project, person, company, risk, or decision."),
    ],
    entity: Annotated[
        str,
        Field(description="Exact entity name, such as Project Atlas."),
    ],
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
) -> list[dict[str, object]]:
    """Return generic dbt mart-backed context for any typed entity."""
    validate_vault_path(vault_path)
    return default_context_service.entity_context_generic(
        None,
        entity_type=entity_type,
        entity=entity,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_entity_events(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity_type: Annotated[
        str | None,
        Field(description="Optional entity type filter."),
    ] = None,
    entity: Annotated[
        str | None,
        Field(description="Optional exact entity name filter."),
    ] = None,
    event_type: Annotated[
        str | None,
        Field(description="Optional event type filter, such as open_loop or task_open."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
) -> list[dict[str, object]]:
    """List generic entity events from the dbt warehouse."""
    validate_vault_path(vault_path)
    return default_context_service.entity_events(
        None,
        entity_type=entity_type,
        entity=entity,
        event_type=event_type,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_entity_relationships(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity_type: Annotated[
        str | None,
        Field(description="Optional entity type filter."),
    ] = None,
    entity: Annotated[
        str | None,
        Field(description="Optional exact entity name filter."),
    ] = None,
    relationship_type: Annotated[
        str | None,
        Field(description="Optional relationship type filter."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
) -> list[dict[str, object]]:
    """List generic relationships between modeled entities."""
    validate_vault_path(vault_path)
    return default_context_service.entity_relationships(
        None,
        entity_type=entity_type,
        entity=entity,
        relationship_type=relationship_type,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_entity_states(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity_type: Annotated[
        str | None,
        Field(description="Optional entity type filter, such as risk or decision."),
    ] = None,
    entity: Annotated[
        str | None,
        Field(description="Optional exact entity name filter."),
    ] = None,
    state_type: Annotated[
        str | None,
        Field(description="Optional state type filter, such as risk_status."),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Optional state value filter, such as open or active."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
) -> list[dict[str, object]]:
    """List generic state rows for stateful entities."""
    validate_vault_path(vault_path)
    return default_context_service.entity_states(
        None,
        entity_type=entity_type,
        entity=entity,
        state_type=state_type,
        status=status,
        limit=_bounded_limit(limit),
    )


@mcp.tool()
def list_vault_entity_open_loops(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    entity_type: Annotated[
        str | None,
        Field(description="Optional entity type filter."),
    ] = None,
    entity: Annotated[
        str | None,
        Field(description="Optional exact entity name filter."),
    ] = None,
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
) -> list[dict[str, object]]:
    """List open loops attached to any modeled entity type."""
    validate_vault_path(vault_path)
    return default_context_service.entity_open_loops(
        None,
        entity_type=entity_type,
        entity=entity,
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
) -> list[dict[str, object]]:
    """Search curated deterministic context rows for agent use."""
    return default_context_service.agent_context(
        vault_path,
        text=text,
        entity=entity,
        event_type=event_type,
        limit=_bounded_limit(limit),
        warehouse_path=None,
    )


@mcp.tool()
def get_vault_project_context(
    vault_path: Annotated[str, Field(description="Path to the Obsidian vault.")],
    project: Annotated[str, Field(description="Project name, such as Project Atlas 1.")],
    limit: Annotated[
        int,
        Field(description=f"Maximum rows to return. Capped at {MAX_LIMIT}.", ge=1),
    ] = 50,
) -> list[dict[str, object]]:
    """Return dbt mart-backed project context, including decisions, risks, and open loops."""
    validate_vault_path(vault_path)
    return default_context_service.project_context(
        None,
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
) -> list[dict[str, object]]:
    """Return dbt mart-backed person context, including decisions, risks, and open loops."""
    validate_vault_path(vault_path)
    return default_context_service.person_context(
        None,
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
) -> list[dict[str, object]]:
    """List dbt mart-backed open loops from unchecked tasks."""
    validate_vault_path(vault_path)
    return default_context_service.open_loops(
        None,
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
) -> list[dict[str, object]]:
    """List dbt mart-backed decisions with optional entity and status filters."""
    validate_vault_path(vault_path)
    return default_context_service.decisions(
        None,
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
) -> list[dict[str, object]]:
    """List dbt mart-backed risks with optional entity and status filters."""
    validate_vault_path(vault_path)
    return default_context_service.risks(
        None,
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
