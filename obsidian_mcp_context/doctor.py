from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path

from obsidian_mcp_context import dbt_warehouse
from obsidian_mcp_context.domain import frontmatter_value, note_title
from obsidian_mcp_context.security import VaultPathError, validate_vault_path
from obsidian_mcp_context.vault import (
    DEFAULT_EXCLUDE_GLOBS,
    DEFAULT_INCLUDE_GLOBS,
    DEFAULT_SOURCE_EXTENSIONS,
    VaultConfig,
    build_context,
    is_excluded,
    is_included,
    normalize_extensions,
)
from obsidian_mcp_context.warehouse import build_warehouse, warehouse_summary


LIFECYCLE_FIELDS = (
    "source_created_at",
    "source_observed_at",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class DoctorOptions:
    vault_path: Path
    duckdb_path: Path | None = None
    strict: bool = False


class DoctorCode(str, Enum):
    VAULT_UNREADABLE = "vault_unreadable"
    NO_MARKDOWN_FILES = "no_markdown_files"
    UNRESOLVED_WIKILINK = "unresolved_wikilink"
    MISSING_LIFECYCLE_METADATA = "missing_lifecycle_metadata"
    MALFORMED_LIFECYCLE_METADATA = "malformed_lifecycle_metadata"
    IGNORED_FILE = "ignored_file"
    UNSUPPORTED_FILE = "unsupported_file"
    EMPTY_NOTE = "empty_note"
    NOTE_WITHOUT_BLOCKS = "note_without_blocks"
    LARGE_NOTE = "large_note"
    WAREHOUSE_BUILD_FAILED = "warehouse_build_failed"
    WAREHOUSE_MISSING = "warehouse_missing"
    WAREHOUSE_INCOMPLETE = "warehouse_incomplete"


@dataclass(frozen=True)
class DiagnosticMessage:
    code: DoctorCode
    severity: str
    message: str
    file_path: str = ""
    details: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["code"] = self.code.value
        row["details"] = self.details or {}
        return row


def _diagnostic(
    diagnostics: list[DiagnosticMessage],
    code: DoctorCode,
    severity: str,
    message: str,
    file_path: str = "",
    details: dict[str, object] | None = None,
) -> None:
    diagnostics.append(
        DiagnosticMessage(
            code=code,
            severity=severity,
            message=message,
            file_path=file_path,
            details=details,
        )
    )


def _iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _scan_inventory(vault_path: Path) -> dict[str, object]:
    source_extensions = set(normalize_extensions(DEFAULT_SOURCE_EXTENSIONS))
    markdown_files: list[str] = []
    ignored_files: list[str] = []
    unsupported_files: list[str] = []
    excluded_files: list[str] = []

    for path in sorted(vault_path.rglob("*")):
        if not path.is_file():
            continue
        source_path = path.relative_to(vault_path).as_posix()
        if is_excluded(source_path, DEFAULT_EXCLUDE_GLOBS):
            excluded_files.append(source_path)
            continue
        if path.suffix.lower() not in source_extensions:
            unsupported_files.append(source_path)
            ignored_files.append(source_path)
            continue
        if not is_included(source_path, DEFAULT_INCLUDE_GLOBS):
            ignored_files.append(source_path)
            continue
        markdown_files.append(source_path)

    return {
        "markdown_files": markdown_files,
        "ignored_files": ignored_files,
        "unsupported_files": unsupported_files,
        "excluded_files": excluded_files,
    }


def run_doctor(options: DoctorOptions) -> dict[str, object]:
    warnings: list[str] = []
    errors: list[str] = []
    diagnostics: list[DiagnosticMessage] = []

    try:
        vault_path = validate_vault_path(options.vault_path)
    except (VaultPathError, FileNotFoundError, OSError) as exc:
        message = str(exc)
        _diagnostic(
            diagnostics,
            DoctorCode.VAULT_UNREADABLE,
            "error",
            message,
            file_path=str(options.vault_path),
        )
        return {
            "status": "error",
            "errors": [message],
            "warnings": [],
            "diagnostics": [item.to_dict() for item in diagnostics],
            "vault": {
                "path": str(options.vault_path),
                "exists": options.vault_path.exists(),
                "readable": False,
            },
        }

    if not vault_path.exists() or not vault_path.is_dir():
        message = f"Vault path is not a readable directory: {vault_path}"
        _diagnostic(
            diagnostics,
            DoctorCode.VAULT_UNREADABLE,
            "error",
            message,
            file_path=str(vault_path),
        )
        return {
            "status": "error",
            "errors": [message],
            "warnings": [],
            "diagnostics": [item.to_dict() for item in diagnostics],
            "vault": {
                "path": str(vault_path),
                "exists": vault_path.exists(),
                "readable": False,
            },
        }

    inventory = _scan_inventory(vault_path)
    context = build_context(VaultConfig(vault_path=vault_path))
    markdown_files = list(inventory["markdown_files"])
    unsupported_files = list(inventory["unsupported_files"])

    if not markdown_files:
        message = "No Markdown files were found with the default vault scan settings."
        errors.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.NO_MARKDOWN_FILES,
            "error",
            message,
            details={"include_globs": list(DEFAULT_INCLUDE_GLOBS)},
        )
    if inventory["ignored_files"]:
        message = f"{len(inventory['ignored_files'])} files were ignored by the vault scan."
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.IGNORED_FILE,
            "warning",
            message,
            details={
                "count": len(inventory["ignored_files"]),
                "sample": list(inventory["ignored_files"])[:25],
            },
        )
    if unsupported_files:
        message = f"{len(unsupported_files)} non-Markdown files will be ignored."
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.UNSUPPORTED_FILE,
            "warning",
            message,
            details={"count": len(unsupported_files), "sample": unsupported_files[:25]},
        )

    blocks_by_source = Counter(block.source_path for block in context.blocks)
    first_block_text_by_source = {
        block.source_path: block.text for block in reversed(context.blocks)
    }
    empty_notes = []
    notes_without_blocks = []
    large_notes = []
    missing_lifecycle = []
    malformed_lifecycle = []

    for source_file in context.files:
        text = source_file.absolute_path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            empty_notes.append(source_file.source_path)
        if blocks_by_source[source_file.source_path] == 0:
            notes_without_blocks.append(source_file.source_path)
        if len(text) > 250_000:
            large_notes.append(source_file.source_path)
        first_block = first_block_text_by_source.get(source_file.source_path)
        missing_fields = [
            field for field in LIFECYCLE_FIELDS if not frontmatter_value(first_block, field)
        ]
        if missing_fields:
            missing_lifecycle.append(
                {"source_path": source_file.source_path, "fields": missing_fields}
            )
        for field in LIFECYCLE_FIELDS:
            value = frontmatter_value(first_block, field)
            if value and not _iso_datetime(value):
                malformed_lifecycle.append(
                    {
                        "source_path": source_file.source_path,
                        "field": field,
                        "value": value,
                    }
                )

    if empty_notes:
        message = f"{len(empty_notes)} Markdown notes are empty."
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.EMPTY_NOTE,
            "warning",
            message,
            details={"count": len(empty_notes), "sample": empty_notes[:25]},
        )
    if notes_without_blocks:
        message = f"{len(notes_without_blocks)} Markdown notes produced no blocks."
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.NOTE_WITHOUT_BLOCKS,
            "warning",
            message,
            details={"count": len(notes_without_blocks), "sample": notes_without_blocks[:25]},
        )
    if large_notes:
        message = f"{len(large_notes)} Markdown notes are larger than 250 KB."
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.LARGE_NOTE,
            "warning",
            message,
            details={"count": len(large_notes), "sample": large_notes[:25]},
        )
    if missing_lifecycle:
        message = (
            f"{len(missing_lifecycle)} notes are missing one or more lifecycle timestamp fields."
        )
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.MISSING_LIFECYCLE_METADATA,
            "warning",
            message,
            details={"count": len(missing_lifecycle), "sample": missing_lifecycle[:25]},
        )
    if malformed_lifecycle:
        message = (
            f"{len(malformed_lifecycle)} lifecycle timestamp values are not ISO datetimes."
        )
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.MALFORMED_LIFECYCLE_METADATA,
            "warning",
            message,
            details={"count": len(malformed_lifecycle), "sample": malformed_lifecycle[:25]},
        )

    note_titles = {note_title(source_path).casefold() for source_path in markdown_files}
    unresolved = [
        link.link_target
        for link in context.links
        if link.link_target.casefold() not in note_titles
    ]
    unresolved_counts = Counter(unresolved)
    if unresolved:
        message = f"{len(unresolved)} wikilinks do not resolve to scanned note titles."
        warnings.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.UNRESOLVED_WIKILINK,
            "warning",
            message,
            details={
                "count": len(unresolved),
                "top_targets": [
                    {"target": target, "count": count}
                    for target, count in unresolved_counts.most_common(10)
                ],
            },
        )

    warehouse_status: dict[str, object]
    try:
        warehouse = build_warehouse(context)
        try:
            in_memory_summary = warehouse_summary(warehouse)
        finally:
            warehouse.close()
        warehouse_status = {
            "in_memory": {"ok": True, "summary": in_memory_summary},
            "duckdb": {"checked": False},
        }
    except Exception as exc:  # pragma: no cover - defensive diagnostic surface
        message = f"In-memory warehouse build failed: {exc}"
        errors.append(message)
        _diagnostic(
            diagnostics,
            DoctorCode.WAREHOUSE_BUILD_FAILED,
            "error",
            message,
        )
        warehouse_status = {
            "in_memory": {"ok": False, "error": str(exc)},
            "duckdb": {"checked": False},
        }

    if options.duckdb_path is not None:
        duckdb_path = options.duckdb_path.expanduser()
        duckdb_ok = dbt_warehouse.is_available(duckdb_path)
        warehouse_status["duckdb"] = {
            "checked": True,
            "path": str(duckdb_path),
            "exists": duckdb_path.exists(),
            "required_marts_available": duckdb_ok,
        }
        if not duckdb_ok:
            if duckdb_path.exists():
                code = DoctorCode.WAREHOUSE_INCOMPLETE
                message = f"DuckDB warehouse is incomplete: {duckdb_path}"
            else:
                code = DoctorCode.WAREHOUSE_MISSING
                message = f"DuckDB warehouse is missing: {duckdb_path}"
            errors.append(message)
            _diagnostic(
                diagnostics,
                code,
                "error",
                message,
                file_path=str(duckdb_path),
            )

    status = "ok"
    if errors:
        status = "error"
    elif warnings:
        status = "warning"

    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "diagnostics": [item.to_dict() for item in diagnostics],
        "vault": {
            "path": str(vault_path),
            "exists": True,
            "readable": True,
            "markdown_file_count": len(markdown_files),
            "ignored_file_count": len(inventory["ignored_files"]),
            "excluded_file_count": len(inventory["excluded_files"]),
        },
        "parser": {
            "files": len(context.files),
            "blocks": len(context.blocks),
            "tasks": len(context.tasks),
            "links": len(context.links),
            "tags": len(context.tags),
            "semantic_lines": len(context.lines),
        },
        "content": {
            "empty_notes": empty_notes[:25],
            "notes_without_blocks": notes_without_blocks[:25],
            "large_notes": large_notes[:25],
            "missing_lifecycle_fields": missing_lifecycle[:25],
            "malformed_lifecycle_fields": malformed_lifecycle[:25],
            "unsupported_files": unsupported_files[:25],
        },
        "graph": {
            "wikilinks": len(context.links),
            "resolved_wikilinks": len(context.links) - len(unresolved),
            "unresolved_wikilinks": len(unresolved),
            "top_unresolved_targets": [
                {"target": target, "count": count}
                for target, count in unresolved_counts.most_common(10)
            ],
        },
        "warehouse": warehouse_status,
    }


def exit_code(report: dict[str, object], strict: bool = False) -> int:
    if report["status"] == "error":
        return 2
    if strict and report["status"] == "warning":
        return 1
    return 0


def format_human(report: dict[str, object]) -> str:
    lines = [
        f"Status: {str(report['status']).upper()}",
    ]
    vault = report.get("vault", {})
    if isinstance(vault, dict):
        lines.append(f"Vault: {vault.get('path')}")
        if "markdown_file_count" in vault:
            lines.append(f"Markdown files: {vault['markdown_file_count']}")
            lines.append(f"Ignored files: {vault['ignored_file_count']}")
    parser = report.get("parser", {})
    if isinstance(parser, dict):
        lines.append(
            "Parsed: "
            f"{parser.get('blocks', 0)} blocks, "
            f"{parser.get('tasks', 0)} tasks, "
            f"{parser.get('links', 0)} links, "
            f"{parser.get('tags', 0)} tags"
        )
    graph = report.get("graph", {})
    if isinstance(graph, dict):
        lines.append(
            "Links: "
            f"{graph.get('resolved_wikilinks', 0)} resolved, "
            f"{graph.get('unresolved_wikilinks', 0)} unresolved"
        )
    warehouse = report.get("warehouse", {})
    if isinstance(warehouse, dict):
        in_memory = warehouse.get("in_memory", {})
        if isinstance(in_memory, dict):
            lines.append(f"In-memory warehouse: {'ok' if in_memory.get('ok') else 'failed'}")
        duckdb = warehouse.get("duckdb", {})
        if isinstance(duckdb, dict) and duckdb.get("checked"):
            lines.append(
                "DuckDB warehouse: "
                f"{'ok' if duckdb.get('required_marts_available') else 'missing/incomplete'}"
            )

    warnings = report.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)

    errors = report.get("errors", [])
    if errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)

    graph = report.get("graph", {})
    if isinstance(graph, dict) and graph.get("top_unresolved_targets"):
        lines.append("")
        lines.append("Top unresolved wikilinks:")
        for row in graph["top_unresolved_targets"]:
            lines.append(f"- {row['target']}: {row['count']}")

    return "\n".join(lines)


def format_json(report: dict[str, object]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)
