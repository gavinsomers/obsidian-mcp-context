from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Iterable

from obsidian_mcp_context import postgres_warehouse
from obsidian_mcp_context.config import load_app_config, vault_config_from_app_config
from obsidian_mcp_context.services import ContextService
from obsidian_mcp_context.vault import build_context


SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RAW_TABLES = (
    "base_obsidian_files",
    "base_obsidian_blocks",
    "base_obsidian_tasks",
    "base_obsidian_links",
    "base_obsidian_tags",
    "base_obsidian_lines",
    "base_obsidian_ingest_profile",
    "base_obsidian_file_observations",
)
DBT_RELATIONS = (
    "stg_obsidian_files",
    "stg_obsidian_blocks",
    "stg_obsidian_tasks",
    "stg_obsidian_links",
    "stg_obsidian_tags",
    "stg_obsidian_lines",
    "stg_obsidian_ingest_profile",
    "dim_notes",
    "fact_blocks",
    "fact_tasks",
    "fact_links",
    "fact_tags",
    "mart_open_loops",
    "mart_entity_context",
    "mart_entity_open_loops",
)
RECONCILIATIONS = (
    ("notes", ("parser", "markdown_files"), ("raw", "base_obsidian_files")),
    ("notes_raw_to_staging", ("raw", "base_obsidian_files"), ("dbt", "stg_obsidian_files")),
    ("notes_staging_to_dim", ("dbt", "stg_obsidian_files"), ("dbt", "dim_notes")),
    ("blocks", ("parser", "blocks"), ("raw", "base_obsidian_blocks")),
    ("blocks_raw_to_fact", ("raw", "base_obsidian_blocks"), ("dbt", "fact_blocks")),
    ("tasks", ("parser", "tasks"), ("raw", "base_obsidian_tasks")),
    ("tasks_raw_to_fact", ("raw", "base_obsidian_tasks"), ("dbt", "fact_tasks")),
    ("links", ("parser", "links"), ("raw", "base_obsidian_links")),
    (
        "links_staging_to_fact_non_expansion",
        ("dbt", "stg_obsidian_links"),
        ("dbt", "fact_links"),
        "less_than_or_equal",
    ),
    ("tags", ("parser", "tags"), ("raw", "base_obsidian_tags")),
    ("tags_raw_to_fact", ("raw", "base_obsidian_tags"), ("dbt", "fact_tags")),
    ("lines", ("parser", "lines"), ("raw", "base_obsidian_lines")),
    (
        "service_dim_notes",
        ("service", "warehouse_dim_notes"),
        ("dbt", "dim_notes"),
    ),
    (
        "service_fact_tasks",
        ("service", "warehouse_fact_tasks"),
        ("dbt", "fact_tasks"),
    ),
    (
        "service_fact_links",
        ("service", "warehouse_fact_links"),
        ("dbt", "fact_links"),
    ),
)


@dataclass(frozen=True)
class CountRef:
    section: str
    key: str


def _validate_schema(schema: str) -> str:
    if not SCHEMA_RE.fullmatch(schema):
        raise ValueError(f"Invalid Postgres schema name: {schema}")
    return schema


def _count_from(report: dict[str, dict[str, int]], ref: tuple[str, str]) -> int | None:
    section, key = ref
    return report.get(section, {}).get(key)


def reconcile_counts(
    *,
    parser_counts: dict[str, int],
    raw_counts: dict[str, int],
    dbt_counts: dict[str, int],
    service_counts: dict[str, int],
) -> list[dict[str, object]]:
    counts = {
        "parser": parser_counts,
        "raw": raw_counts,
        "dbt": dbt_counts,
        "service": service_counts,
    }
    checks: list[dict[str, object]] = []
    for reconciliation in RECONCILIATIONS:
        name = reconciliation[0]
        left_ref = reconciliation[1]
        right_ref = reconciliation[2]
        operator = reconciliation[3] if len(reconciliation) > 3 else "equal"
        left_value = _count_from(counts, left_ref)
        right_value = _count_from(counts, right_ref)
        if left_value is None or right_value is None:
            status = "fail"
        elif operator == "less_than_or_equal":
            status = "pass" if right_value <= left_value else "fail"
        else:
            status = "pass" if left_value == right_value else "fail"
        checks.append(
            {
                "name": name,
                "operator": operator,
                "left": {"section": left_ref[0], "key": left_ref[1], "value": left_value},
                "right": {
                    "section": right_ref[0],
                    "key": right_ref[1],
                    "value": right_value,
                },
                "status": status,
            }
        )
    return checks


def collect_parser_counts(vault_path: Path, profile_path: str | None = None) -> dict[str, int]:
    app_config = load_app_config(profile_path=profile_path)
    vault_config = vault_config_from_app_config(vault_path, app_config)
    context = build_context(vault_config)
    return {
        "markdown_files": len(context.files),
        "blocks": len(context.blocks),
        "tasks": len(context.tasks),
        "links": len(context.links),
        "tags": len(context.tags),
        "lines": len(context.lines),
    }


def _relation_counts(
    postgres_dsn: str,
    relations: Iterable[str],
    *,
    schema: str | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    with postgres_warehouse.connect(postgres_dsn) as connection:
        for relation in relations:
            if schema:
                relation_sql = f"{_validate_schema(schema)}.{relation}"
            else:
                relation_sql = relation
            row = connection.execute(f"select count(*) as count from {relation_sql}").fetchone()
            counts[relation] = int(row[0])
    return counts


def collect_raw_counts(postgres_dsn: str, raw_schema: str) -> dict[str, int]:
    return _relation_counts(postgres_dsn, RAW_TABLES, schema=raw_schema)


def collect_dbt_counts(postgres_dsn: str) -> dict[str, int]:
    return _relation_counts(postgres_dsn, DBT_RELATIONS)


def collect_service_counts(
    vault_path: Path,
    postgres_dsn: str,
    profile_path: str | None = None,
) -> dict[str, int]:
    app_config = load_app_config(profile_path=profile_path)
    service = ContextService(app_config=app_config)
    warehouse = service.warehouse_summary(vault_path, postgres_dsn=postgres_dsn)
    tables = warehouse.get("tables", {}) if isinstance(warehouse, dict) else {}
    return {
        "warehouse_dim_notes": int(tables.get("dim_notes", -1)),
        "warehouse_fact_tasks": int(tables.get("fact_tasks", -1)),
        "warehouse_fact_links": int(tables.get("fact_links", -1)),
    }


def build_reconciliation_report(
    *,
    vault_path: Path,
    postgres_dsn: str,
    raw_schema: str = "raw",
    profile_path: str | None = None,
) -> dict[str, object]:
    parser_counts = collect_parser_counts(vault_path, profile_path=profile_path)
    raw_counts = collect_raw_counts(postgres_dsn, raw_schema)
    dbt_counts = collect_dbt_counts(postgres_dsn)
    service_counts = collect_service_counts(
        vault_path,
        postgres_dsn,
        profile_path=profile_path,
    )
    checks = reconcile_counts(
        parser_counts=parser_counts,
        raw_counts=raw_counts,
        dbt_counts=dbt_counts,
        service_counts=service_counts,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_name": vault_path.name,
        "privacy": {
            "aggregate_counts_only": True,
            "absolute_paths_redacted": True,
            "note_text_included": False,
        },
        "counts": {
            "parser": parser_counts,
            "raw": raw_counts,
            "dbt": dbt_counts,
            "service": service_counts,
        },
        "checks": checks,
        "summary": {
            "status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
            "check_count": len(checks),
            "failed_count": sum(1 for check in checks if check["status"] != "pass"),
        },
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Pipeline Reconciliation Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Vault snapshot: `{report['vault_name']}`",
        f"Status: `{summary['status']}`",
        f"Checks: {summary['check_count']}",
        f"Failed: {summary['failed_count']}",
        "",
        "## Checks",
    ]
    for check in report["checks"]:
        left = check["left"]
        right = check["right"]
        lines.append(
            "- "
            f"{check['status'].upper()}: `{check['name']}` "
            f"{left['section']}.{left['key']}={left['value']} "
            f"vs {right['section']}.{right['key']}={right['value']}"
        )
    lines.extend(
        [
            "",
            "## Privacy",
            "This report contains aggregate counts only. It does not include note text, "
            "raw rows, or absolute vault paths.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-reconcile-pipeline",
        description="Compare parser, raw Postgres, dbt, and service aggregate counts.",
    )
    parser.add_argument("--vault", required=True, help="Vault snapshot path.")
    parser.add_argument("--postgres-dsn", default=None, help="Postgres DSN.")
    parser.add_argument("--raw-schema", default="raw", help="Raw landing schema.")
    parser.add_argument("--vault-profile", default=None, help="Vault profile path or name.")
    parser.add_argument("--output-json", default=None, help="Optional JSON report path.")
    parser.add_argument("--output-md", default=None, help="Optional Markdown report path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    postgres_dsn = postgres_warehouse.resolve_postgres_dsn(args.postgres_dsn)
    if not postgres_dsn:
        raise SystemExit("POSTGRES_DSN or --postgres-dsn is required")
    vault_path = Path(args.vault).expanduser().resolve()
    report = build_reconciliation_report(
        vault_path=vault_path,
        postgres_dsn=postgres_dsn,
        raw_schema=args.raw_schema,
        profile_path=args.vault_profile or os.environ.get("OBSIDIAN_MCP_VAULT_PROFILE"),
    )
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output_md:
        Path(args.output_md).write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
