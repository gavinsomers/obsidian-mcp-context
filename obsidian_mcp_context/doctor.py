from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from pathlib import PurePosixPath
import re

from obsidian_mcp_context import dbt_warehouse
from obsidian_mcp_context.config import load_app_config, vault_config_from_app_config
from obsidian_mcp_context.domain import frontmatter_value, note_title
from obsidian_mcp_context.security import VaultPathError, validate_vault_path
from obsidian_mcp_context.vault import (
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
FRONTMATTER_BODY_RE = re.compile(r"(?ms)\A\s*---(?P<body>.*?)^---\s*$")
FRONTMATTER_LIST_ITEM_RE = re.compile(r"^\s*-\s*[\"']?(.+?)[\"']?\s*$")
DATE_LIKE_TARGET_RE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
URL_LIKE_TARGET_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


@dataclass(frozen=True)
class DoctorOptions:
    vault_path: Path
    duckdb_path: Path | None = None
    strict: bool = False
    config_path: Path | None = None
    include_samples: bool = False


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


def _sample_details(
    count: int,
    sample: object,
    *,
    include_samples: bool,
    sample_key: str = "sample",
) -> dict[str, object]:
    details: dict[str, object] = {"count": count}
    if include_samples:
        details[sample_key] = sample
    else:
        details["samples_redacted"] = True
    return details


def _iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _clean_frontmatter_scalar(value: str) -> str:
    return value.strip().strip("\"'")


def _frontmatter_list_values(text: str | None, field: str) -> list[str]:
    if not text:
        return []
    frontmatter_match = FRONTMATTER_BODY_RE.search(text)
    if not frontmatter_match:
        return []

    lines = frontmatter_match.group("body").splitlines()
    values: list[str] = []
    collecting_block = False
    for line in lines:
        if not line.strip():
            continue
        field_match = re.match(rf"^{re.escape(field)}:\s*(.*)$", line)
        if field_match:
            raw_value = field_match.group(1).strip()
            collecting_block = raw_value == ""
            if raw_value.startswith("[") and raw_value.endswith("]"):
                inner = raw_value[1:-1]
                values.extend(
                    _clean_frontmatter_scalar(item)
                    for item in inner.split(",")
                    if _clean_frontmatter_scalar(item)
                )
            elif raw_value:
                values.append(_clean_frontmatter_scalar(raw_value))
            continue
        if collecting_block:
            item_match = FRONTMATTER_LIST_ITEM_RE.match(line)
            if item_match:
                value = _clean_frontmatter_scalar(item_match.group(1))
                if value:
                    values.append(value)
                continue
            if not line.startswith((" ", "\t", "-")):
                collecting_block = False
    return values


def _link_resolution_key(value: str) -> str:
    target = value.split("#", 1)[0].split("^", 1)[0].strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target.casefold()


def _note_resolution_keys(source_path: str, first_block_text: str | None) -> set[str]:
    path_without_extension = source_path[:-3] if source_path.endswith(".md") else source_path
    keys = {
        note_title(source_path).casefold(),
        source_path.casefold(),
        path_without_extension.casefold(),
    }
    for alias_field in ("alias", "aliases"):
        for alias in _frontmatter_list_values(first_block_text, alias_field):
            keys.add(_link_resolution_key(alias))
    return {key for key in keys if key}


def _link_target_shape(value: str) -> str:
    target = value.strip()
    if URL_LIKE_TARGET_RE.match(target):
        return "url_like"
    if "#" in target:
        return "heading_reference"
    if "^" in target:
        return "block_reference"
    if "/" in target or target.endswith(".md"):
        return "path_like"
    if DATE_LIKE_TARGET_RE.search(target):
        return "date_like"
    return "plain_text"


def _shape_counts(values: list[str]) -> dict[str, int]:
    counts = Counter(_link_target_shape(value) for value in values)
    return dict(sorted(counts.items()))


def _path_like_resolution_target(value: str) -> str:
    target = value.split("#", 1)[0].split("^", 1)[0].strip().strip("/")
    if target.endswith(".md"):
        target = target[:-3]
    return target


def _path_with_markdown_extension(value: str) -> str:
    return value if value.casefold().endswith(".md") else f"{value}.md"


def _path_stem_key(value: str) -> str:
    path = PurePosixPath(value)
    return str(path.with_suffix("")).casefold() if path.suffix else value.casefold()


def _basename_stem_key(value: str) -> str:
    path = PurePosixPath(value)
    name = path.name
    suffix = PurePosixPath(name).suffix
    return name[: -len(suffix)].casefold() if suffix else name.casefold()


def _classify_path_like_unresolved_targets(
    unresolved: list[str], inventory: dict[str, object]
) -> dict[str, int]:
    markdown_files = [str(item) for item in inventory["markdown_files"]]
    ignored_files = [str(item) for item in inventory["ignored_files"]]
    excluded_files = [str(item) for item in inventory["excluded_files"]]
    unsupported_files = [str(item) for item in inventory["unsupported_files"]]

    scanned_paths = {item.casefold() for item in markdown_files}
    ignored_paths = {item.casefold() for item in ignored_files}
    excluded_paths = {item.casefold() for item in excluded_files}
    unsupported_paths = {item.casefold() for item in unsupported_files}
    unsupported_stems = {_path_stem_key(item) for item in unsupported_files}
    scanned_basenames = {_basename_stem_key(item) for item in markdown_files}

    reasons: Counter[str] = Counter()
    for target in unresolved:
        if _link_target_shape(target) != "path_like":
            continue
        path_target = _path_like_resolution_target(target)
        if not path_target:
            reasons["no_candidate_found"] += 1
            continue
        explicit_path = target.split("#", 1)[0].split("^", 1)[0].strip().strip("/")
        markdown_path = _path_with_markdown_extension(path_target)
        exact_key = explicit_path.casefold()
        markdown_key = markdown_path.casefold()
        target_stem = _path_stem_key(explicit_path)

        if exact_key in excluded_paths or markdown_key in excluded_paths:
            reasons["excluded_path"] += 1
        elif exact_key in unsupported_paths or target_stem in unsupported_stems:
            reasons["unsupported_extension"] += 1
        elif markdown_key in ignored_paths and markdown_key not in scanned_paths:
            reasons["missing_extension_candidate"] += 1
        elif _basename_stem_key(markdown_path) in scanned_basenames:
            reasons["basename_exists_elsewhere"] += 1
        else:
            reasons["no_candidate_found"] += 1

    return dict(sorted(reasons.items()))


def _scan_inventory(vault_path: Path, config: VaultConfig) -> dict[str, object]:
    source_extensions = set(normalize_extensions(config.source_extensions))
    markdown_files: list[str] = []
    ignored_files: list[str] = []
    unsupported_files: list[str] = []
    excluded_files: list[str] = []

    for path in sorted(vault_path.rglob("*")):
        if not path.is_file():
            continue
        source_path = path.relative_to(vault_path).as_posix()
        if is_excluded(source_path, config.exclude_globs):
            excluded_files.append(source_path)
            continue
        if path.suffix.lower() not in source_extensions:
            unsupported_files.append(source_path)
            continue
        if not is_included(source_path, config.include_globs):
            ignored_files.append(source_path)
            continue
        markdown_files.append(source_path)

    return {
        "markdown_files": markdown_files,
        "ignored_files": ignored_files,
        "unsupported_files": unsupported_files,
        "excluded_files": excluded_files,
    }


def _record_policy_diagnostic(
    *,
    mode: str,
    warnings: list[str],
    errors: list[str],
    diagnostics: list[DiagnosticMessage],
    code: DoctorCode,
    message: str,
    count: int,
    sample: object,
    include_samples: bool,
    sample_key: str = "sample",
    details: dict[str, object] | None = None,
) -> None:
    if mode == "ignore":
        return
    severity = "error" if mode == "error" else "warning"
    if severity == "error":
        errors.append(message)
    else:
        warnings.append(message)
    _diagnostic(
        diagnostics,
        code,
        severity,
        message,
        details=details
        or _sample_details(
            count,
            sample,
            include_samples=include_samples,
            sample_key=sample_key,
        ),
    )


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

    app_config = load_app_config(options.config_path)
    vault_config = vault_config_from_app_config(vault_path, app_config)
    inventory = _scan_inventory(vault_path, vault_config)
    context = build_context(vault_config)
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
            details={"include_globs": list(vault_config.include_globs)},
        )
    if inventory["ignored_files"]:
        message = f"{len(inventory['ignored_files'])} files were ignored by the vault scan."
        _record_policy_diagnostic(
            mode=app_config.doctor_ignored_files,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.IGNORED_FILE,
            message=message,
            count=len(inventory["ignored_files"]),
            sample=list(inventory["ignored_files"])[:25],
            include_samples=options.include_samples,
        )
    if unsupported_files:
        message = f"{len(unsupported_files)} non-Markdown files will be ignored."
        _record_policy_diagnostic(
            mode=app_config.doctor_unsupported_files,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.UNSUPPORTED_FILE,
            message=message,
            count=len(unsupported_files),
            sample=unsupported_files[:25],
            include_samples=options.include_samples,
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
        _record_policy_diagnostic(
            mode=app_config.doctor_empty_notes,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.EMPTY_NOTE,
            message=message,
            count=len(empty_notes),
            sample=empty_notes[:25],
            include_samples=options.include_samples,
        )
    if notes_without_blocks:
        message = f"{len(notes_without_blocks)} Markdown notes produced no blocks."
        _record_policy_diagnostic(
            mode=app_config.doctor_notes_without_blocks,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.NOTE_WITHOUT_BLOCKS,
            message=message,
            count=len(notes_without_blocks),
            sample=notes_without_blocks[:25],
            include_samples=options.include_samples,
        )
    if large_notes:
        message = f"{len(large_notes)} Markdown notes are larger than 250 KB."
        _record_policy_diagnostic(
            mode=app_config.doctor_large_notes,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.LARGE_NOTE,
            message=message,
            count=len(large_notes),
            sample=large_notes[:25],
            include_samples=options.include_samples,
        )
    if missing_lifecycle:
        message = (
            f"{len(missing_lifecycle)} notes are missing one or more lifecycle timestamp fields."
        )
        _record_policy_diagnostic(
            mode=app_config.doctor_lifecycle_metadata,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.MISSING_LIFECYCLE_METADATA,
            message=message,
            count=len(missing_lifecycle),
            sample=missing_lifecycle[:25],
            include_samples=options.include_samples,
        )
    if malformed_lifecycle:
        message = (
            f"{len(malformed_lifecycle)} lifecycle timestamp values are not ISO datetimes."
        )
        _record_policy_diagnostic(
            mode=app_config.doctor_lifecycle_metadata,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.MALFORMED_LIFECYCLE_METADATA,
            message=message,
            count=len(malformed_lifecycle),
            sample=malformed_lifecycle[:25],
            include_samples=options.include_samples,
        )

    resolvable_link_targets: set[str] = set()
    for source_file in context.files:
        resolvable_link_targets.update(
            _note_resolution_keys(
                source_file.source_path,
                first_block_text_by_source.get(source_file.source_path),
            )
        )
    unresolved = [
        link.link_target
        for link in context.links
        if _link_resolution_key(link.link_target) not in resolvable_link_targets
    ]
    unresolved_counts = Counter(unresolved)
    unresolved_shapes = _shape_counts(unresolved)
    unresolved_path_like_reasons = _classify_path_like_unresolved_targets(
        unresolved, inventory
    )
    if unresolved:
        message = f"{len(unresolved)} wikilinks do not resolve to scanned note titles."
        unresolved_details = _sample_details(
            len(unresolved),
            [
                {"target": target, "count": count}
                for target, count in unresolved_counts.most_common(10)
            ],
            include_samples=options.include_samples,
            sample_key="top_targets",
        )
        unresolved_details["target_shapes"] = unresolved_shapes
        unresolved_details["path_like_reasons"] = unresolved_path_like_reasons
        _record_policy_diagnostic(
            mode=app_config.doctor_unresolved_wikilinks,
            warnings=warnings,
            errors=errors,
            diagnostics=diagnostics,
            code=DoctorCode.UNRESOLVED_WIKILINK,
            message=message,
            count=len(unresolved),
            sample=[],
            include_samples=options.include_samples,
            details=unresolved_details,
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
        "privacy": {
            "samples_included": options.include_samples,
            "samples_redacted": not options.include_samples,
        },
        "vault": {
            "path": str(vault_path),
            "exists": True,
            "readable": True,
            "markdown_file_count": len(markdown_files),
            "ignored_file_count": len(inventory["ignored_files"]),
            "excluded_file_count": len(inventory["excluded_files"]),
        },
        "config": {
            "path": str(app_config.config_path) if app_config.config_path else None,
            "loaded": app_config.loaded,
            "include_globs": list(vault_config.include_globs),
            "exclude_globs": list(vault_config.exclude_globs),
            "source_extensions": list(vault_config.source_extensions),
            "folder_note_type_count": len(vault_config.folder_note_types or {}),
            "non_entity_note_types": list(vault_config.non_entity_note_types or ()),
            "doctor": {
                "lifecycle_metadata": app_config.doctor_lifecycle_metadata,
                "ignored_files": app_config.doctor_ignored_files,
                "unsupported_files": app_config.doctor_unsupported_files,
                "empty_notes": app_config.doctor_empty_notes,
                "notes_without_blocks": app_config.doctor_notes_without_blocks,
                "large_notes": app_config.doctor_large_notes,
                "unresolved_wikilinks": app_config.doctor_unresolved_wikilinks,
            },
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
            "empty_note_count": len(empty_notes),
            "notes_without_blocks_count": len(notes_without_blocks),
            "large_note_count": len(large_notes),
            "missing_lifecycle_field_count": len(missing_lifecycle),
            "malformed_lifecycle_field_count": len(malformed_lifecycle),
            "unsupported_file_count": len(unsupported_files),
            "empty_notes": empty_notes[:25] if options.include_samples else [],
            "notes_without_blocks": notes_without_blocks[:25] if options.include_samples else [],
            "large_notes": large_notes[:25] if options.include_samples else [],
            "missing_lifecycle_fields": (
                missing_lifecycle[:25] if options.include_samples else []
            ),
            "malformed_lifecycle_fields": (
                malformed_lifecycle[:25] if options.include_samples else []
            ),
            "unsupported_files": unsupported_files[:25] if options.include_samples else [],
        },
        "graph": {
            "wikilinks": len(context.links),
            "resolved_wikilinks": len(context.links) - len(unresolved),
            "unresolved_wikilinks": len(unresolved),
            "unresolved_target_shapes": unresolved_shapes,
            "unresolved_path_like_reasons": unresolved_path_like_reasons,
            "top_unresolved_targets": [
                {"target": target, "count": count}
                for target, count in unresolved_counts.most_common(10)
            ]
            if options.include_samples
            else [],
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
