from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from obsidian_mcp_context.config import load_app_config, vault_config_from_app_config
from obsidian_mcp_context.domain import frontmatter_value
from obsidian_mcp_context.parser import WIKILINK_RE
from obsidian_mcp_context.security import validate_vault_path
from obsidian_mcp_context.vault import (
    VaultConfig,
    build_context,
    is_excluded,
    is_included,
    normalize_extensions,
    scan_vault,
    to_vault_relative,
)


DEFAULT_PROFILE_REPORT_PATH = Path("var/vault-profile-report.json")
FRONTMATTER_RE = re.compile(r"(?ms)\A\s*---(?P<body>.*?)^---\s*")
FRONTMATTER_KEY_RE = re.compile(r"(?m)^([A-Za-z_][A-Za-z0-9_-]*):")
LIFECYCLE_FIELDS = (
    "source_created_at",
    "source_observed_at",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class ProfilerOptions:
    vault_path: Path
    config_path: Path | None = None
    profile_path: Path | None = None
    output_path: Path = DEFAULT_PROFILE_REPORT_PATH
    include_samples: bool = False


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _sample(values: list[str], *, include_samples: bool, limit: int = 5) -> list[str]:
    if not include_samples:
        return []
    return sorted(values)[:limit]


def _frontmatter_keys(text: str) -> set[str]:
    match = FRONTMATTER_RE.search(text)
    if not match:
        return set()
    return {key for key in FRONTMATTER_KEY_RE.findall(match.group("body"))}


def _wikilink_shape(raw: str) -> str:
    target = raw.split("|", 1)[0].split("#", 1)[0].split("^", 1)[0].strip()
    if not target:
        return "empty"
    if "/" in target or target.endswith(".md"):
        return "path_like"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", target):
        return "date_like"
    return "title_like"


def _count_all_vault_files(config: VaultConfig) -> dict[str, object]:
    vault_path = validate_vault_path(config.vault_path)
    source_extensions = set(normalize_extensions(config.source_extensions))
    extension_counts: Counter[str] = Counter()
    ignored_paths: list[str] = []
    unsupported_paths: list[str] = []
    included_candidates = 0

    for path in sorted(vault_path.rglob("*")):
        if not path.is_file():
            continue
        source_path = to_vault_relative(path, vault_path)
        extension = path.suffix.lower() or "(none)"
        extension_counts[extension] += 1
        if is_excluded(source_path, config.exclude_globs):
            ignored_paths.append(source_path)
            continue
        if is_included(source_path, config.include_globs):
            included_candidates += 1
            if path.suffix.lower() not in source_extensions:
                unsupported_paths.append(source_path)

    return {
        "all_file_count": sum(extension_counts.values()),
        "included_candidate_count": included_candidates,
        "ignored_file_count": len(ignored_paths),
        "unsupported_included_file_count": len(unsupported_paths),
        "extensions": _counter_dict(extension_counts),
        "ignored_path_samples": ignored_paths,
        "unsupported_path_samples": unsupported_paths,
    }


def profile_vault(options: ProfilerOptions) -> dict[str, object]:
    app_config = load_app_config(options.config_path, profile_path=options.profile_path)
    vault_config = vault_config_from_app_config(options.vault_path, app_config)
    validate_vault_path(vault_config.vault_path)
    source_files = scan_vault(vault_config)
    context = build_context(vault_config)

    folder_counts: Counter[str] = Counter()
    note_type_counts: Counter[str] = Counter()
    frontmatter_key_counts: Counter[str] = Counter()
    lifecycle_counts: Counter[str] = Counter()
    wikilink_shapes: Counter[str] = Counter()
    empty_notes: list[str] = []
    large_notes: list[str] = []
    frontmatter_file_count = 0
    total_bytes = 0

    for source_file in source_files:
        source_path = source_file.source_path
        folder_counts[source_path.split("/", 1)[0] if "/" in source_path else "(root)"] += 1
        note_type_counts[source_file.note_type] += 1

        text = source_file.absolute_path.read_text(encoding="utf-8", errors="replace")
        total_bytes += len(text.encode("utf-8"))
        if not text.strip():
            empty_notes.append(source_path)
        if len(text) > 25_000:
            large_notes.append(source_path)

        keys = _frontmatter_keys(text)
        if keys:
            frontmatter_file_count += 1
        frontmatter_key_counts.update(keys)
        for field in LIFECYCLE_FIELDS:
            if frontmatter_value(text, field):
                lifecycle_counts[field] += 1

        for link_match in WIKILINK_RE.finditer(text):
            wikilink_shapes[_wikilink_shape(link_match.group(1))] += 1

    all_file_counts = _count_all_vault_files(vault_config)
    tag_counts = Counter(tag.tag for tag in context.tags)

    return {
        "type": "vault_profile_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": {
            "read_only": True,
            "source_paths_redacted": not options.include_samples,
            "note_content_included": False,
        },
        "config": {
            "profile_loaded": app_config.profile_path is not None,
            "config_loaded": app_config.loaded,
            "profile_path": (
                str(app_config.profile_path)
                if options.include_samples and app_config.profile_path
                else ""
            ),
            "config_path": (
                str(app_config.config_path)
                if options.include_samples and app_config.config_path
                else ""
            ),
            "include_globs": list(vault_config.include_globs),
            "exclude_globs": list(vault_config.exclude_globs),
            "source_extensions": list(vault_config.source_extensions),
            "folder_note_type_count": len(vault_config.folder_note_types or {}),
            "non_entity_note_types": list(vault_config.non_entity_note_types or ()),
        },
        "files": {
            **{
                key: value
                for key, value in all_file_counts.items()
                if not key.endswith("_samples")
            },
            "scanned_source_file_count": len(source_files),
            "total_scanned_bytes": total_bytes,
            "folders": _counter_dict(folder_counts),
            "note_types": _counter_dict(note_type_counts),
        },
        "frontmatter": {
            "files_with_frontmatter": frontmatter_file_count,
            "coverage_ratio": (
                round(frontmatter_file_count / len(source_files), 4)
                if source_files
                else 0.0
            ),
            "keys": _counter_dict(frontmatter_key_counts),
            "lifecycle_field_coverage": {
                field: {
                    "count": lifecycle_counts[field],
                    "coverage_ratio": (
                        round(lifecycle_counts[field] / len(source_files), 4)
                        if source_files
                        else 0.0
                    ),
                }
                for field in LIFECYCLE_FIELDS
            },
        },
        "graph": {
            "wikilinks": len(context.links),
            "wikilink_shapes": _counter_dict(wikilink_shapes),
            "tags": len(context.tags),
            "unique_tags": len(tag_counts),
            "top_tags": _counter_dict(Counter(dict(tag_counts.most_common(20)))),
        },
        "content": {
            "blocks": len(context.blocks),
            "lines": len(context.lines),
            "tasks": len(context.tasks),
            "empty_note_count": len(empty_notes),
            "large_note_count": len(large_notes),
        },
        "samples": {
            "redacted": not options.include_samples,
            "ignored_paths": _sample(
                list(all_file_counts["ignored_path_samples"]),
                include_samples=options.include_samples,
            ),
            "unsupported_paths": _sample(
                list(all_file_counts["unsupported_path_samples"]),
                include_samples=options.include_samples,
            ),
            "empty_notes": _sample(empty_notes, include_samples=options.include_samples),
            "large_notes": _sample(large_notes, include_samples=options.include_samples),
        },
        "recommendations": _recommendations(
            source_file_count=len(source_files),
            unsupported_file_count=int(all_file_counts["unsupported_included_file_count"]),
            frontmatter_coverage=(
                frontmatter_file_count / len(source_files) if source_files else 0.0
            ),
            lifecycle_counts=lifecycle_counts,
            empty_note_count=len(empty_notes),
        ),
    }


def _recommendations(
    *,
    source_file_count: int,
    unsupported_file_count: int,
    frontmatter_coverage: float,
    lifecycle_counts: Counter[str],
    empty_note_count: int,
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    if source_file_count == 0:
        recommendations.append(
            {
                "code": "no_scanned_sources",
                "message": "Review include globs, exclude globs, source extensions, and vault path.",
            }
        )
    if unsupported_file_count:
        recommendations.append(
            {
                "code": "unsupported_included_files",
                "message": "Review source_extensions or include globs for included files with unsupported extensions.",
            }
        )
    if source_file_count and frontmatter_coverage < 0.5:
        recommendations.append(
            {
                "code": "low_frontmatter_coverage",
                "message": "Consider whether this vault needs filename/folder-derived metadata rather than frontmatter assumptions.",
            }
        )
    missing_lifecycle = [
        field for field in LIFECYCLE_FIELDS if lifecycle_counts[field] < source_file_count
    ]
    if source_file_count and missing_lifecycle:
        recommendations.append(
            {
                "code": "missing_lifecycle_metadata",
                "message": "Profile or downstream marts should tolerate missing lifecycle fields: "
                + ", ".join(missing_lifecycle),
            }
        )
    if empty_note_count:
        recommendations.append(
            {
                "code": "empty_notes",
                "message": "Decide whether empty notes should be excluded, retained as stubs, or fixed upstream.",
            }
        )
    return recommendations


def write_profile_report(report: dict[str, object], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-profile-vault",
        description="Write a read-only aggregate profile report for a vault.",
    )
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault.")
    parser.add_argument(
        "--config",
        help="Optional .obsidian-mcp-context.toml path for local scan and entity settings.",
    )
    parser.add_argument(
        "--vault-profile",
        help="Optional vault profile TOML path or checked-in profile name.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_PROFILE_REPORT_PATH),
        help="Report output path. Defaults to var/vault-profile-report.json.",
    )
    parser.add_argument(
        "--include-samples",
        action="store_true",
        help="Include a few local source-path samples. Never includes note content.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = profile_vault(
        ProfilerOptions(
            vault_path=Path(args.vault),
            config_path=Path(args.config) if args.config else None,
            profile_path=Path(args.vault_profile) if args.vault_profile else None,
            output_path=Path(args.output),
            include_samples=args.include_samples,
        )
    )
    output_path = write_profile_report(report, Path(args.output))
    print(f"Vault profile report written to {output_path}")
    return 0
