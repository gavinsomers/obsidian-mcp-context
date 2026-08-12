from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from fnmatch import fnmatchcase
import json
from pathlib import Path
from pathlib import PurePosixPath
import re

from obsidian_mcp_context.config import (
    PROJECT_ROOT,
    load_app_config,
    vault_config_from_app_config,
)
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
UNRESOLVED_REASON_HINTS = {
    "excluded_path": (
        "adjust_scan_excludes",
        "Review scan excludes for linked notes that exist under excluded paths.",
    ),
    "unsupported_extension": (
        "include_extension",
        "Review source extensions for linked files that exist with unsupported extensions.",
    ),
    "missing_extension_candidate": (
        "adjust_scan_includes",
        "Review scan include globs for Markdown candidates outside the scanned set.",
    ),
    "basename_exists_elsewhere": (
        "normalize_link_path",
        "Update links whose basename exists elsewhere but not at the linked path.",
    ),
    "no_candidate_found": (
        "create_note",
        "Create missing notes or remove links with no matching candidate.",
    ),
}


@dataclass(frozen=True)
class DoctorOptions:
    vault_path: Path
    strict: bool = False
    config_path: Path | None = None
    profile_path: Path | None = None
    include_samples: bool = False
    export_unresolved_path: Path | None = None


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
    UNRESOLVED_EXPORT_FAILED = "unresolved_export_failed"


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


def _note_resolution_keys(source_path: str, note_text: str | None) -> set[str]:
    path_without_extension = source_path[:-3] if source_path.endswith(".md") else source_path
    keys = {
        note_title(source_path, note_text).casefold(),
        source_path.casefold(),
        path_without_extension.casefold(),
    }
    for alias_field in ("alias", "aliases"):
        for alias in _frontmatter_list_values(note_text, alias_field):
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


def _matches_target_glob(target: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return False
    stripped = target.strip()
    candidates = {
        stripped,
        stripped.split("#", 1)[0].split("^", 1)[0].strip(),
        _link_resolution_key(stripped),
    }
    return any(
        fnmatchcase(candidate.casefold(), pattern.casefold())
        for candidate in candidates
        for pattern in patterns
    )


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


def _path_like_reason_inventory(inventory: dict[str, object]) -> dict[str, set[str]]:
    markdown_files = [str(item) for item in inventory["markdown_files"]]
    ignored_files = [str(item) for item in inventory["ignored_files"]]
    excluded_files = [str(item) for item in inventory["excluded_files"]]
    unsupported_files = [str(item) for item in inventory["unsupported_files"]]

    return {
        "scanned_paths": {item.casefold() for item in markdown_files},
        "ignored_paths": {item.casefold() for item in ignored_files},
        "excluded_paths": {item.casefold() for item in excluded_files},
        "unsupported_paths": {item.casefold() for item in unsupported_files},
        "unsupported_stems": {_path_stem_key(item) for item in unsupported_files},
        "scanned_basenames": {_basename_stem_key(item) for item in markdown_files},
    }


def _path_like_unresolved_reason(
    target: str, reason_inventory: dict[str, set[str]]
) -> str:
    path_target = _path_like_resolution_target(target)
    if not path_target:
        return "no_candidate_found"
    explicit_path = target.split("#", 1)[0].split("^", 1)[0].strip().strip("/")
    markdown_path = _path_with_markdown_extension(path_target)
    exact_key = explicit_path.casefold()
    markdown_key = markdown_path.casefold()
    target_stem = _path_stem_key(explicit_path)

    if (
        exact_key in reason_inventory["excluded_paths"]
        or markdown_key in reason_inventory["excluded_paths"]
    ):
        return "excluded_path"
    if (
        exact_key in reason_inventory["unsupported_paths"]
        or target_stem in reason_inventory["unsupported_stems"]
    ):
        return "unsupported_extension"
    if (
        markdown_key in reason_inventory["ignored_paths"]
        and markdown_key not in reason_inventory["scanned_paths"]
    ):
        return "missing_extension_candidate"
    if _basename_stem_key(markdown_path) in reason_inventory["scanned_basenames"]:
        return "basename_exists_elsewhere"
    return "no_candidate_found"


def _classify_path_like_unresolved_targets(
    unresolved: list[str], inventory: dict[str, object]
) -> dict[str, int]:
    reason_inventory = _path_like_reason_inventory(inventory)

    reasons: Counter[str] = Counter()
    for target in unresolved:
        if _link_target_shape(target) != "path_like":
            continue
        reasons[_path_like_unresolved_reason(target, reason_inventory)] += 1

    return dict(sorted(reasons.items()))


def _unresolved_remediation_hints(
    *,
    path_like_reasons: dict[str, int],
    target_shapes: dict[str, int],
    ignored_count: int,
) -> list[dict[str, object]]:
    hints: list[dict[str, object]] = []
    for reason, count in path_like_reasons.items():
        if count <= 0 or reason not in UNRESOLVED_REASON_HINTS:
            continue
        code, message = UNRESOLVED_REASON_HINTS[reason]
        hints.append(
            {
                "code": code,
                "count": count,
                "source": f"path_like_reason:{reason}",
                "message": message,
            }
        )
    non_path_like_count = sum(
        count for shape, count in target_shapes.items() if shape != "path_like"
    )
    if non_path_like_count > 0:
        hints.append(
            {
                "code": "create_note",
                "count": non_path_like_count,
                "source": "target_shape:non_path_like",
                "message": (
                    "Create missing notes or remove unresolved non-path wikilinks."
                ),
            }
        )
    if ignored_count > 0:
        hints.append(
            {
                "code": "review_ignored_patterns",
                "count": ignored_count,
                "source": "ignored_unresolved_wikilinks",
                "message": (
                    "Review unresolved ignore patterns periodically to confirm they "
                    "still describe intentional dangling links."
                ),
            }
        )
    return hints


def _safe_export_path(path: Path) -> Path:
    export_path = path.expanduser()
    if not export_path.is_absolute():
        export_path = Path.cwd() / export_path
    resolved = export_path.resolve()
    cwd = Path.cwd().resolve()
    try:
        relative = resolved.relative_to(cwd)
    except ValueError:
        return resolved
    if relative.parts and relative.parts[0] == "var":
        return resolved
    raise ValueError(
        "Unresolved-link exports may contain private target names; write them "
        "outside the repository or under the ignored var/ directory."
    )


def _write_unresolved_export(
    *,
    path: Path,
    unresolved_targets: list[dict[str, object]],
    include_samples: bool,
) -> dict[str, object]:
    export_path = _safe_export_path(path)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "privacy": {
            "contains_private_targets": True,
            "contains_source_paths": include_samples,
            "intended_for_local_use_only": True,
        },
        "unresolved_target_count": len(unresolved_targets),
        "unresolved_targets": unresolved_targets,
    }
    export_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "written": True,
        "target_count": len(unresolved_targets),
        "path": str(export_path),
    }


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


def _readiness_check(
    *,
    name: str,
    status: str,
    message: str,
    blocking: bool = False,
    signals: dict[str, object] | None = None,
    actions: list[str] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "status": status,
        "blocking": blocking,
        "message": message,
        "signals": signals or {},
        "actions": actions or [],
    }


def _readiness_report(
    *,
    status: str,
    errors: list[str],
    warnings: list[str],
    checks: list[dict[str, object]],
) -> dict[str, object]:
    suggestions: list[str] = []
    for check in checks:
        for action in check.get("actions", []):
            if isinstance(action, str) and action not in suggestions:
                suggestions.append(action)
    return {
        "status": "blocked" if status == "error" else status,
        "blocking": bool(errors)
        or any(bool(check.get("blocking")) for check in checks),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "blocking_errors": list(errors),
        "checks": checks,
        "suggestions": suggestions,
    }


def _unreadable_readiness(
    *,
    message: str,
    path: Path,
    exists: bool,
) -> dict[str, object]:
    return _readiness_report(
        status="error",
        errors=[message],
        warnings=[],
        checks=[
            _readiness_check(
                name="vault_access",
                status="blocked",
                blocking=True,
                message="Vault path is not readable.",
                signals={
                    "path": str(path),
                    "exists": exists,
                    "readable": False,
                },
                actions=[
                    "Provide a readable vault path with --vault.",
                    "Check local filesystem permissions before running ingest or MCP.",
                ],
            )
        ],
    )


def _build_readiness_checks(
    *,
    app_config: object,
    vault_status: dict[str, object],
    parser_status: dict[str, object],
    content_status: dict[str, object],
    graph_status: dict[str, object],
    warehouse_status: dict[str, object],
    dbt_project_path: Path,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []

    profile_loaded = bool(getattr(app_config, "profile_path", None))
    config_loaded = bool(getattr(app_config, "loaded", False))
    checks.append(
        _readiness_check(
            name="profile",
            status="ready" if profile_loaded else "warning",
            message=(
                "Vault profile is loaded."
                if profile_loaded
                else "No vault profile is loaded; defaults may not match this vault."
            ),
            signals={
                "profile_loaded": profile_loaded,
                "config_loaded": config_loaded,
                "folder_note_type_count": vault_status.get("folder_note_type_count", 0),
            },
            actions=[]
            if profile_loaded
            else ["Select a vault profile with --vault-profile for non-demo vault runs."],
        )
    )

    markdown_count = int(vault_status.get("markdown_file_count", 0))
    unsupported_count = int(content_status.get("unsupported_file_count", 0))
    ignored_count = int(vault_status.get("ignored_file_count", 0))
    vault_actions = []
    if markdown_count == 0:
        vault_actions.append("Review scan include/exclude globs so Markdown files are scanned.")
    if unsupported_count:
        vault_actions.append("Review unsupported files and source_extensions.")
    if ignored_count:
        vault_actions.append("Review ignored files to confirm scan patterns are intentional.")
    checks.append(
        _readiness_check(
            name="vault_access",
            status="blocked" if markdown_count == 0 else ("warning" if vault_actions else "ready"),
            blocking=markdown_count == 0,
            message=(
                "Vault has readable Markdown files."
                if markdown_count
                else "Vault has no scanned Markdown files."
            ),
            signals={
                "markdown_file_count": markdown_count,
                "ignored_file_count": ignored_count,
                "excluded_file_count": vault_status.get("excluded_file_count", 0),
                "unsupported_file_count": unsupported_count,
            },
            actions=vault_actions,
        )
    )

    parser_files = int(parser_status.get("files", 0))
    parser_blocks = int(parser_status.get("blocks", 0))
    checks.append(
        _readiness_check(
            name="parser",
            status="ready" if parser_files and parser_blocks else "blocked",
            blocking=not (parser_files and parser_blocks),
            message=(
                "Parser produced notes and blocks."
                if parser_files and parser_blocks
                else "Parser did not produce usable note/block rows."
            ),
            signals=parser_status,
            actions=[]
            if parser_files and parser_blocks
            else ["Inspect empty notes, source extensions, and Markdown parsing errors."],
        )
    )

    content_actions = []
    if content_status.get("missing_lifecycle_field_count"):
        content_actions.append("Add or map lifecycle timestamp fields where useful.")
    if content_status.get("empty_note_count"):
        content_actions.append("Review empty notes and decide whether they should be excluded.")
    if content_status.get("large_note_count"):
        content_actions.append("Review oversized notes before MCP retrieval.")
    if content_status.get("notes_without_blocks_count"):
        content_actions.append("Review notes that produced no blocks.")
    if content_status.get("malformed_lifecycle_field_count"):
        content_actions.append("Fix malformed lifecycle timestamp values.")
    checks.append(
        _readiness_check(
            name="content",
            status="warning" if content_actions else "ready",
            message=(
                "Content checks found improvement opportunities."
                if content_actions
                else "Content checks passed without warnings."
            ),
            signals={
                "empty_note_count": content_status.get("empty_note_count", 0),
                "notes_without_blocks_count": content_status.get(
                    "notes_without_blocks_count", 0
                ),
                "large_note_count": content_status.get("large_note_count", 0),
                "missing_lifecycle_field_count": content_status.get(
                    "missing_lifecycle_field_count", 0
                ),
                "malformed_lifecycle_field_count": content_status.get(
                    "malformed_lifecycle_field_count", 0
                ),
            },
            actions=content_actions,
        )
    )

    graph_actions = []
    if graph_status.get("warning_unresolved_wikilinks"):
        graph_actions.append("Review unresolved wikilinks or export a local unresolved-link report.")
    if graph_status.get("ignored_unresolved_wikilinks"):
        graph_actions.append("Periodically review ignored unresolved wikilink patterns.")
    checks.append(
        _readiness_check(
            name="graph",
            status="warning" if graph_actions else "ready",
            message=(
                "Graph checks found unresolved wikilinks."
                if graph_actions
                else "Graph links are ready."
            ),
            signals={
                "wikilinks": graph_status.get("wikilinks", 0),
                "resolved_wikilinks": graph_status.get("resolved_wikilinks", 0),
                "warning_unresolved_wikilinks": graph_status.get(
                    "warning_unresolved_wikilinks", 0
                ),
                "ignored_unresolved_wikilinks": graph_status.get(
                    "ignored_unresolved_wikilinks", 0
                ),
            },
            actions=graph_actions,
        )
    )

    in_memory = warehouse_status.get("in_memory", {})
    warehouse_ok = isinstance(in_memory, dict) and bool(in_memory.get("ok"))
    checks.append(
        _readiness_check(
            name="warehouse",
            status="ready" if warehouse_ok else "blocked",
            blocking=not warehouse_ok,
            message=(
                "In-memory warehouse builds successfully."
                if warehouse_ok
                else "In-memory warehouse build failed."
            ),
            signals=in_memory if isinstance(in_memory, dict) else {},
            actions=[]
            if warehouse_ok
            else ["Fix parser or warehouse build errors before relying on marts."],
        )
    )

    dbt_present = dbt_project_path.exists()
    checks.append(
        _readiness_check(
            name="dbt",
            status="not_checked" if dbt_present else "blocked",
            blocking=not dbt_present,
            message=(
                "dbt project is present; run dbt build/test after Postgres ingest."
                if dbt_present
                else "dbt project file is missing."
            ),
            signals={
                "project_path": str(dbt_project_path),
                "project_present": dbt_present,
            },
            actions=[
                "Run Postgres ingest and dbt build/test for mart-backed readiness."
            ]
            if dbt_present
            else ["Restore dbt_project.yml before warehouse mart validation."],
        )
    )

    mcp_ready = parser_files > 0 and warehouse_ok
    checks.append(
        _readiness_check(
            name="mcp",
            status="ready" if mcp_ready else "blocked",
            blocking=not mcp_ready,
            message=(
                "MCP can use parsed context and warehouse-backed diagnostics."
                if mcp_ready
                else "MCP readiness is blocked by parser or warehouse issues."
            ),
            signals={
                "parser_files": parser_files,
                "warehouse_ok": warehouse_ok,
                "samples_redacted_by_default": True,
            },
            actions=[]
            if mcp_ready
            else ["Resolve parser and warehouse readiness blockers before MCP use."],
        )
    )

    return checks


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
            "readiness": _unreadable_readiness(
                message=message,
                path=options.vault_path,
                exists=options.vault_path.exists(),
            ),
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
            "readiness": _unreadable_readiness(
                message=message,
                path=vault_path,
                exists=vault_path.exists(),
            ),
            "diagnostics": [item.to_dict() for item in diagnostics],
            "vault": {
                "path": str(vault_path),
                "exists": vault_path.exists(),
                "readable": False,
            },
        }

    app_config = load_app_config(
        options.config_path,
        profile_path=options.profile_path,
    )
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
                source_file.absolute_path.read_text(
                    encoding="utf-8", errors="replace"
                ),
            )
        )
    unresolved_links = [
        link
        for link in context.links
        if _link_resolution_key(link.link_target) not in resolvable_link_targets
    ]
    ignored_unresolved_links = [
        link
        for link in unresolved_links
        if _matches_target_glob(
            link.link_target,
            app_config.doctor_unresolved_wikilink_ignore_target_globs,
        )
    ]
    warning_unresolved_links = [
        link
        for link in unresolved_links
        if not _matches_target_glob(
            link.link_target,
            app_config.doctor_unresolved_wikilink_ignore_target_globs,
        )
    ]
    unresolved = [link.link_target for link in unresolved_links]
    ignored_unresolved = [link.link_target for link in ignored_unresolved_links]
    warning_unresolved = [link.link_target for link in warning_unresolved_links]
    unresolved_counts = Counter(unresolved)
    warning_unresolved_counts = Counter(warning_unresolved)
    unresolved_sources: dict[str, set[str]] = {}
    for link in unresolved_links:
        unresolved_sources.setdefault(link.link_target, set()).add(link.source_path)
    unresolved_shapes = _shape_counts(unresolved)
    ignored_unresolved_shapes = _shape_counts(ignored_unresolved)
    warning_unresolved_shapes = _shape_counts(warning_unresolved)
    unresolved_path_like_reasons = _classify_path_like_unresolved_targets(
        unresolved, inventory
    )
    ignored_unresolved_path_like_reasons = _classify_path_like_unresolved_targets(
        ignored_unresolved, inventory
    )
    warning_unresolved_path_like_reasons = _classify_path_like_unresolved_targets(
        warning_unresolved, inventory
    )
    unresolved_remediation_hints = _unresolved_remediation_hints(
        path_like_reasons=warning_unresolved_path_like_reasons,
        target_shapes=warning_unresolved_shapes,
        ignored_count=len(ignored_unresolved),
    )
    path_like_reason_inventory = _path_like_reason_inventory(inventory)
    unresolved_export_targets: list[dict[str, object]] = []
    for target, count in unresolved_counts.most_common():
        target_shape = _link_target_shape(target)
        row: dict[str, object] = {
            "target": target,
            "target_shape": target_shape,
            "reason": (
                _path_like_unresolved_reason(target, path_like_reason_inventory)
                if target_shape == "path_like"
                else ""
            ),
            "count": count,
            "ignored": _matches_target_glob(
                target,
                app_config.doctor_unresolved_wikilink_ignore_target_globs,
            ),
            "source_count": len(unresolved_sources.get(target, set())),
        }
        if options.include_samples:
            row["source_paths"] = sorted(unresolved_sources.get(target, set()))
        unresolved_export_targets.append(row)
    unresolved_export: dict[str, object] = {
        "requested": options.export_unresolved_path is not None,
        "written": False,
    }
    if options.export_unresolved_path is not None:
        try:
            unresolved_export = {
                "requested": True,
                **_write_unresolved_export(
                    path=options.export_unresolved_path,
                    unresolved_targets=unresolved_export_targets,
                    include_samples=options.include_samples,
                ),
            }
        except OSError as exc:
            message = f"Failed to write unresolved wikilink export: {exc}"
            errors.append(message)
            _diagnostic(
                diagnostics,
                DoctorCode.UNRESOLVED_EXPORT_FAILED,
                "error",
                message,
            )
            unresolved_export = {
                "requested": True,
                "written": False,
                "error": str(exc),
            }
        except ValueError as exc:
            message = str(exc)
            errors.append(message)
            _diagnostic(
                diagnostics,
                DoctorCode.UNRESOLVED_EXPORT_FAILED,
                "error",
                message,
            )
            unresolved_export = {
                "requested": True,
                "written": False,
                "error": message,
            }
    if warning_unresolved:
        message = (
            f"{len(warning_unresolved)} wikilinks do not resolve to scanned note titles."
        )
        unresolved_details = _sample_details(
            len(warning_unresolved),
            [
                {"target": target, "count": count}
                for target, count in warning_unresolved_counts.most_common(10)
            ],
            include_samples=options.include_samples,
            sample_key="top_targets",
        )
        unresolved_details["target_shapes"] = warning_unresolved_shapes
        unresolved_details["path_like_reasons"] = warning_unresolved_path_like_reasons
        unresolved_details["ignored_count"] = len(ignored_unresolved)
        unresolved_details["ignored_target_shapes"] = ignored_unresolved_shapes
        unresolved_details["remediation_hints"] = unresolved_remediation_hints
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
        }

    status = "ok"
    if errors:
        status = "error"
    elif warnings:
        status = "warning"

    vault_status = {
        "path": str(vault_path),
        "exists": True,
        "readable": True,
        "markdown_file_count": len(markdown_files),
        "ignored_file_count": len(inventory["ignored_files"]),
        "excluded_file_count": len(inventory["excluded_files"]),
        "folder_note_type_count": len(vault_config.folder_note_types or {}),
    }
    config_status = {
        "path": str(app_config.config_path) if app_config.config_path else None,
        "profile_path": (
            str(app_config.profile_path) if app_config.profile_path else None
        ),
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
            "unresolved_wikilink_ignore_target_globs": list(
                app_config.doctor_unresolved_wikilink_ignore_target_globs
            ),
        },
    }
    parser_status = {
        "files": len(context.files),
        "blocks": len(context.blocks),
        "tasks": len(context.tasks),
        "links": len(context.links),
        "tags": len(context.tags),
        "semantic_lines": len(context.lines),
    }
    content_status = {
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
    }
    graph_status = {
        "wikilinks": len(context.links),
        "resolved_wikilinks": len(context.links) - len(unresolved),
        "unresolved_wikilinks": len(unresolved),
        "ignored_unresolved_wikilinks": len(ignored_unresolved),
        "warning_unresolved_wikilinks": len(warning_unresolved),
        "unresolved_target_shapes": unresolved_shapes,
        "ignored_unresolved_target_shapes": ignored_unresolved_shapes,
        "warning_unresolved_target_shapes": warning_unresolved_shapes,
        "unresolved_path_like_reasons": unresolved_path_like_reasons,
        "ignored_unresolved_path_like_reasons": (
            ignored_unresolved_path_like_reasons
        ),
        "warning_unresolved_path_like_reasons": (
            warning_unresolved_path_like_reasons
        ),
        "unresolved_remediation_hints": unresolved_remediation_hints,
        "unresolved_export": unresolved_export,
        "top_unresolved_targets": [
            {"target": target, "count": count}
            for target, count in unresolved_counts.most_common(10)
        ]
        if options.include_samples
        else [],
    }
    readiness = _readiness_report(
        status=status,
        errors=errors,
        warnings=warnings,
        checks=_build_readiness_checks(
            app_config=app_config,
            vault_status=vault_status,
            parser_status=parser_status,
            content_status=content_status,
            graph_status=graph_status,
            warehouse_status=warehouse_status,
            dbt_project_path=PROJECT_ROOT / "dbt_project.yml",
        ),
    )

    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "readiness": readiness,
        "diagnostics": [item.to_dict() for item in diagnostics],
        "privacy": {
            "samples_included": options.include_samples,
            "samples_redacted": not options.include_samples,
        },
        "vault": vault_status,
        "config": config_status,
        "parser": parser_status,
        "content": content_status,
        "graph": graph_status,
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
    readiness = report.get("readiness", {})
    if isinstance(readiness, dict):
        lines.append(
            "Readiness: "
            f"{str(readiness.get('status', 'unknown')).upper()} "
            f"({readiness.get('warning_count', 0)} warnings, "
            f"{readiness.get('error_count', 0)} errors)"
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
    if isinstance(graph, dict) and graph.get("unresolved_remediation_hints"):
        lines.append("")
        lines.append("Unresolved wikilink remediation hints:")
        for row in graph["unresolved_remediation_hints"]:
            lines.append(f"- {row['code']}: {row['count']} ({row['message']})")
    if isinstance(readiness, dict) and readiness.get("suggestions"):
        lines.append("")
        lines.append("Readiness suggestions:")
        for suggestion in readiness["suggestions"]:
            lines.append(f"- {suggestion}")

    return "\n".join(lines)


def format_json(report: dict[str, object]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)
