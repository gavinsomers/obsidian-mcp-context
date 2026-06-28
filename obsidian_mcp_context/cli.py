from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidian_mcp_context.config import load_app_config, vault_config_from_app_config
from obsidian_mcp_context.doctor import (
    DoctorOptions,
    exit_code,
    format_human,
    format_json,
    run_doctor,
)
from obsidian_mcp_context.query import list_notes, list_tasks, search_blocks
from obsidian_mcp_context.vault import build_context
from obsidian_mcp_context.warehouse import (
    agent_context,
    build_warehouse,
    entity_timeline,
    list_entities,
    warehouse_summary,
)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context",
        description="Inspect generic context extracted from an Obsidian vault.",
    )
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault.")
    parser.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path for local scan and entity settings.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    notes = subparsers.add_parser("notes", help="List parsed notes.")
    notes.add_argument("--limit", type=int, default=100)

    blocks = subparsers.add_parser("blocks", help="Search parsed blocks.")
    blocks.add_argument("--text")
    blocks.add_argument("--source-path")
    blocks.add_argument("--heading")
    blocks.add_argument("--limit", type=int, default=25)

    tasks = subparsers.add_parser("tasks", help="List parsed tasks.")
    tasks.add_argument("--checked", action="store_true")
    tasks.add_argument("--unchecked", action="store_true")
    tasks.add_argument("--text")
    tasks.add_argument("--source-path")
    tasks.add_argument("--limit", type=int, default=50)

    warehouse = subparsers.add_parser(
        "warehouse-summary", help="Summarize deterministic warehouse tables."
    )

    entities = subparsers.add_parser("entities", help="List modeled entities.")
    entities.add_argument("--entity-type")
    entities.add_argument("--text")
    entities.add_argument("--limit", type=int, default=100)

    timeline = subparsers.add_parser(
        "timeline", help="Show deterministic timeline rows for an entity."
    )
    timeline.add_argument("--entity", required=True)
    timeline.add_argument("--text")
    timeline.add_argument("--limit", type=int, default=50)

    agent = subparsers.add_parser(
        "agent-context", help="Query curated warehouse context rows."
    )
    agent.add_argument("--text")
    agent.add_argument("--entity")
    agent.add_argument("--event-type")
    agent.add_argument("--limit", type=int, default=25)

    doctor = subparsers.add_parser(
        "doctor", help="Validate a vault for parser, graph, and warehouse readiness."
    )
    doctor.add_argument("--json", action="store_true", help="Print a machine-readable report.")
    doctor.add_argument("--strict", action="store_true", help="Return non-zero on warnings.")
    doctor.add_argument("--duckdb", help="Optional DuckDB warehouse path to validate.")
    doctor.add_argument(
        "--include-samples",
        action="store_true",
        help="Include note paths, file paths, and unresolved link targets in doctor output.",
    )
    doctor.add_argument(
        "--export-unresolved",
        help=(
            "Write local-private unresolved wikilink targets to an explicit JSON path. "
            "Use an ignored path such as var/unresolved-links.json."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        report = run_doctor(
            DoctorOptions(
                vault_path=Path(args.vault),
                duckdb_path=Path(args.duckdb) if args.duckdb else None,
                strict=args.strict,
                config_path=Path(args.config) if args.config else None,
                include_samples=args.include_samples,
                export_unresolved_path=(
                    Path(args.export_unresolved) if args.export_unresolved else None
                ),
            )
        )
        print(format_json(report) if args.json else format_human(report))
        return exit_code(report, strict=args.strict)

    app_config = load_app_config(Path(args.config) if args.config else None)
    context = build_context(vault_config_from_app_config(Path(args.vault), app_config))

    if args.command == "notes":
        _print_json(list_notes(context, limit=args.limit))
        return 0

    if args.command == "blocks":
        _print_json(
            search_blocks(
                context,
                text=args.text,
                source_path=args.source_path,
                heading=args.heading,
                limit=args.limit,
            )
        )
        return 0

    if args.command == "tasks":
        checked = None
        if args.checked:
            checked = True
        if args.unchecked:
            checked = False
        _print_json(
            list_tasks(
                context,
                checked=checked,
                text=args.text,
                source_path=args.source_path,
                limit=args.limit,
            )
        )
        return 0

    if args.command == "warehouse-summary":
        warehouse = build_warehouse(context)
        _print_json(warehouse_summary(warehouse))
        return 0

    if args.command == "entities":
        warehouse = build_warehouse(context)
        _print_json(
            list_entities(
                warehouse,
                entity_type=args.entity_type,
                text=args.text,
                limit=args.limit,
            )
        )
        return 0

    if args.command == "timeline":
        warehouse = build_warehouse(context)
        _print_json(
            entity_timeline(
                warehouse,
                entity=args.entity,
                text=args.text,
                limit=args.limit,
            )
        )
        return 0

    if args.command == "agent-context":
        warehouse = build_warehouse(context)
        _print_json(
            agent_context(
                warehouse,
                text=args.text,
                entity=args.entity,
                event_type=args.event_type,
                limit=args.limit,
            )
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
