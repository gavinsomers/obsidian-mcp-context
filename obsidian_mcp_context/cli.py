from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from obsidian_mcp_context.config import load_app_config, vault_config_from_app_config
from obsidian_mcp_context.doctor import (
    DoctorOptions,
    exit_code,
    format_human,
    format_json,
    run_doctor,
)
from obsidian_mcp_context.pipeline import (
    PipelineConfigError,
    run_pipeline,
    run_pipeline_doctor,
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


def _fallback_warning(command: str) -> None:
    print(
        (
            f"Warning: no valid Postgres/dbt warehouse was found for {command}; "
            "falling back to direct parser diagnostics. Build the warehouse with "
            "obsidian-mcp-context-ingest-postgres and dbt for normal use."
        ),
        file=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context",
        description="Inspect generic context extracted from an Obsidian vault.",
    )
    parser.add_argument("--vault", help="Path to the Obsidian vault.")
    parser.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path for local scan and entity settings.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline = subparsers.add_parser("pipeline", help="Run configured pipeline jobs.")
    pipeline_subparsers = pipeline.add_subparsers(
        dest="pipeline_command", required=True
    )

    pipeline_run = pipeline_subparsers.add_parser(
        "run", help="Run the configured deterministic pipeline."
    )
    pipeline_run.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path with pipeline settings.",
    )
    pipeline_run.add_argument(
        "--profile",
        help="Named example profile from examples/config, such as sample.",
    )
    pipeline_run.add_argument(
        "--include-private-paths",
        action="store_true",
        help="Include local source/config paths and doctor samples in output.",
    )

    pipeline_doctor = pipeline_subparsers.add_parser(
        "doctor", help="Run doctor against the configured pipeline source."
    )
    pipeline_doctor.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path with pipeline settings.",
    )
    pipeline_doctor.add_argument(
        "--profile",
        help="Named example profile from examples/config, such as sample.",
    )
    pipeline_doctor.add_argument("--json", action="store_true")
    pipeline_doctor.add_argument("--strict", action="store_true")
    pipeline_doctor.add_argument(
        "--include-private-paths",
        action="store_true",
        help="Include local source/config paths and doctor samples in output.",
    )

    notes = subparsers.add_parser("notes", help="Diagnostic: list directly parsed notes.")
    notes.add_argument("--limit", type=int, default=100)

    blocks = subparsers.add_parser("blocks", help="Diagnostic: search directly parsed blocks.")
    blocks.add_argument("--text")
    blocks.add_argument("--source-path")
    blocks.add_argument("--heading")
    blocks.add_argument("--limit", type=int, default=25)

    tasks = subparsers.add_parser("tasks", help="Diagnostic: list directly parsed tasks.")
    tasks.add_argument("--checked", action="store_true")
    tasks.add_argument("--unchecked", action="store_true")
    tasks.add_argument("--text")
    tasks.add_argument("--source-path")
    tasks.add_argument("--limit", type=int, default=50)

    subparsers.add_parser(
        "warehouse-summary", help="Summarize diagnostic parser warehouse rows."
    )

    entities = subparsers.add_parser("entities", help="List modeled entities from marts.")
    entities.add_argument("--entity-type")
    entities.add_argument("--text")
    entities.add_argument("--limit", type=int, default=100)

    timeline = subparsers.add_parser(
        "timeline", help="Show mart-backed timeline/context rows for an entity."
    )
    timeline.add_argument("--entity", required=True)
    timeline.add_argument("--text")
    timeline.add_argument("--limit", type=int, default=50)

    agent = subparsers.add_parser(
        "agent-context", help="Query curated mart context rows."
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

    if args.command == "pipeline":
        try:
            if args.pipeline_command == "run":
                report = run_pipeline(
                    config_path=args.config,
                    profile=args.profile,
                    include_private_paths=args.include_private_paths,
                )
                output_path = report.pop("output_path")
                _print_json(report)
                print(f"Pipeline run report written to {output_path}")
                return 0 if report["status"] != "error" else 2
            if args.pipeline_command == "doctor":
                report = run_pipeline_doctor(
                    config_path=args.config,
                    profile=args.profile,
                    strict=args.strict,
                    include_private_paths=args.include_private_paths,
                )
                print(format_json(report) if args.json else format_human(report))
                return exit_code(report, strict=args.strict)
        except PipelineConfigError as exc:
            parser.error(str(exc))

    if args.command == "doctor":
        if not args.vault:
            parser.error("--vault is required for doctor")
        report = run_doctor(
            DoctorOptions(
                vault_path=Path(args.vault),
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

    if not args.vault:
        parser.error(f"--vault is required for {args.command}")

    if args.command == "notes":
        app_config = load_app_config(Path(args.config) if args.config else None)
        context = build_context(vault_config_from_app_config(Path(args.vault), app_config))
        _print_json(list_notes(context, limit=args.limit))
        return 0

    if args.command == "blocks":
        app_config = load_app_config(Path(args.config) if args.config else None)
        context = build_context(vault_config_from_app_config(Path(args.vault), app_config))
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
        app_config = load_app_config(Path(args.config) if args.config else None)
        context = build_context(vault_config_from_app_config(Path(args.vault), app_config))
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

    app_config = load_app_config(Path(args.config) if args.config else None)
    context = build_context(vault_config_from_app_config(Path(args.vault), app_config))

    if args.command == "warehouse-summary":
        _fallback_warning(args.command)
        warehouse = build_warehouse(context)
        _print_json(warehouse_summary(warehouse))
        return 0

    if args.command == "entities":
        _fallback_warning(args.command)
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
        _fallback_warning(args.command)
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
        _fallback_warning(args.command)
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
