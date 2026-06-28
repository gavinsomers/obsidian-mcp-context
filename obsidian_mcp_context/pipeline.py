from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from obsidian_mcp_context.ai import AIProviderError, build_ai_provider
from obsidian_mcp_context.config import AppConfig, DEFAULT_CONFIG_PATH, load_app_config
from obsidian_mcp_context.config import vault_config_from_app_config
from obsidian_mcp_context.doctor import DoctorOptions, run_doctor
from obsidian_mcp_context.enrichment import AIEnrichmentStats
from obsidian_mcp_context.enrichment import run_unresolved_link_ai_enrichment
from obsidian_mcp_context.vault import build_context
from obsidian_mcp_context.warehouse import build_warehouse, warehouse_summary


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / "examples" / "config"
SAMPLE_DIR = PROJECT_ROOT / "examples"
PIPELINE_RUN_FILENAME = "pipeline-run.json"
REDACTED = "[redacted]"


class PipelineConfigError(ValueError):
    """Raised when a pipeline profile cannot resolve to a runnable source."""


def profile_config_path(profile: str) -> Path:
    path = PROFILE_DIR / f"{profile}.toml"
    if not path.exists():
        raise PipelineConfigError(f"Unknown pipeline profile: {profile}")
    return path


def load_pipeline_config(
    *,
    config_path: str | Path | None = None,
    profile: str | None = None,
) -> AppConfig:
    if config_path and profile:
        raise PipelineConfigError("Pass either --config or --profile, not both")
    if profile:
        return load_app_config(profile_config_path(profile))
    return load_app_config(Path(config_path) if config_path else DEFAULT_CONFIG_PATH)


def resolve_source_path(config: AppConfig) -> Path:
    if config.source.type == "sample":
        path = SAMPLE_DIR / config.source.sample_name
    elif config.source.type == "obsidian":
        path = Path(config.source.vault_path).expanduser()
    elif config.source.type == "google_drive":
        raise PipelineConfigError("source.type google_drive is not implemented yet")
    else:
        raise PipelineConfigError(f"Unsupported source type: {config.source.type}")

    if not path.exists():
        raise PipelineConfigError(f"Source path does not exist: {path}")
    if not path.is_dir():
        raise PipelineConfigError(f"Source path is not a directory: {path}")
    return path


def _display_path(path: Path, *, include_private_paths: bool) -> str:
    return str(path) if include_private_paths else REDACTED


def _source_summary(
    config: AppConfig,
    source_path: Path,
    *,
    include_private_paths: bool,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "type": config.source.type,
        "exists": source_path.exists(),
        "path": _display_path(source_path, include_private_paths=include_private_paths),
        "path_redacted": not include_private_paths,
    }
    if config.source.type == "sample":
        summary["sample_name"] = config.source.sample_name
    return summary


def _doctor_summary(report: dict[str, object]) -> dict[str, object]:
    parser = report.get("parser", {})
    graph = report.get("graph", {})
    content = report.get("content", {})
    warehouse = report.get("warehouse", {})
    return {
        "status": report.get("status"),
        "error_count": len(report.get("errors", [])),
        "warning_count": len(report.get("warnings", [])),
        "parser": parser if isinstance(parser, dict) else {},
        "graph": {
            "wikilinks": graph.get("wikilinks", 0) if isinstance(graph, dict) else 0,
            "resolved_wikilinks": (
                graph.get("resolved_wikilinks", 0) if isinstance(graph, dict) else 0
            ),
            "unresolved_wikilinks": (
                graph.get("unresolved_wikilinks", 0) if isinstance(graph, dict) else 0
            ),
            "ignored_unresolved_wikilinks": (
                graph.get("ignored_unresolved_wikilinks", 0)
                if isinstance(graph, dict)
                else 0
            ),
        },
        "content": {
            "empty_note_count": (
                content.get("empty_note_count", 0) if isinstance(content, dict) else 0
            ),
            "unsupported_file_count": (
                content.get("unsupported_file_count", 0)
                if isinstance(content, dict)
                else 0
            ),
            "large_note_count": (
                content.get("large_note_count", 0) if isinstance(content, dict) else 0
            ),
        },
        "warehouse": warehouse if isinstance(warehouse, dict) else {},
    }


def _sanitize_private_paths(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key in {"path", "file_path", "absolute_path"}:
                sanitized[key] = REDACTED if item else item
            else:
                sanitized[key] = _sanitize_private_paths(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_private_paths(item) for item in value]
    return value


def sanitize_report(
    report: dict[str, object],
    *,
    include_private_paths: bool,
) -> dict[str, object]:
    if include_private_paths:
        return deepcopy(report)
    return _sanitize_private_paths(report)


def ai_posture(
    config: AppConfig,
    enrichment_stats: AIEnrichmentStats | None = None,
) -> dict[str, object]:
    configured = False
    configuration_error = ""
    if not config.ai.enabled:
        configured = True
    else:
        try:
            build_ai_provider(config)
            configured = True
        except AIProviderError as exc:
            configuration_error = str(exc)
    stats = enrichment_stats or AIEnrichmentStats()
    return {
        "enabled": config.ai.enabled,
        "provider": config.ai.provider,
        "model": config.ai.model,
        "configured": configured,
        "configuration_error": configuration_error,
        "hosted": config.ai.provider in {"openai", "anthropic"},
        "raw_text_allowed": config.privacy.allow_raw_text_to_ai,
        "hosted_ai_allowed": config.privacy.allow_hosted_ai,
        "max_context_chars": config.privacy.max_context_chars,
        "redact_file_paths": config.privacy.redact_file_paths,
        **stats.to_dict(),
    }


def suggestion_counts(warehouse_report: dict[str, object]) -> dict[str, int]:
    tables = warehouse_report.get("tables", {})
    deterministic_count = 0
    if isinstance(tables, dict):
        deterministic_count = int(tables.get("deterministic_suggested_links", 0))
        ai_count = int(tables.get("ai_suggested_links", 0))
    else:
        ai_count = 0
    return {
        "deterministic_suggested_links": deterministic_count,
        "ai_suggested_links": ai_count,
        "ai_related_notes": 0,
        "ai_entity_alias_suggestions": 0,
    }


def privacy_posture(
    config: AppConfig,
    *,
    include_private_paths: bool,
    output_path: Path,
    enrichment_stats: AIEnrichmentStats,
) -> dict[str, object]:
    output_under_configured_dir = False
    try:
        output_path.resolve().relative_to(Path(config.pipeline.output_dir).resolve())
        output_under_configured_dir = True
    except ValueError:
        output_under_configured_dir = False
    return {
        "raw_text_to_ai_allowed": config.privacy.allow_raw_text_to_ai,
        "hosted_ai_allowed": config.privacy.allow_hosted_ai,
        "redact_file_paths": config.privacy.redact_file_paths,
        "private_paths_in_report": include_private_paths,
        "samples_included": include_private_paths,
        "runtime_state_path": _display_path(
            output_path,
            include_private_paths=include_private_paths,
        ),
        "runtime_state_path_redacted": not include_private_paths,
        "runtime_state_under_configured_output_dir": output_under_configured_dir,
        "ai_calls": enrichment_stats.calls,
        "ai_suggestions_written": enrichment_stats.suggestions_written,
        "ai_skipped_due_to_privacy": enrichment_stats.skipped_due_to_privacy,
        "ai_skipped_due_to_budget": enrichment_stats.skipped_due_to_budget,
        "ai_skipped_due_to_provider_error": (
            enrichment_stats.skipped_due_to_provider_error
        ),
        "ai_skipped_due_to_invalid_candidate": (
            enrichment_stats.skipped_due_to_invalid_candidate
        ),
        "ai_skipped_no_candidate": enrichment_stats.skipped_no_candidate,
    }


def review_summary(warehouse_report: dict[str, object]) -> dict[str, object]:
    tables = warehouse_report.get("tables", {})
    if not isinstance(tables, dict):
        tables = {}
    return {
        "deterministic_suggested_links": {
            "pending_count": int(tables.get("deterministic_suggested_links", 0)),
            "contains_source_paths": False,
        },
        "ai_suggested_links": {
            "pending_count": int(tables.get("ai_suggested_links", 0)),
            "reviewed_status": "pending",
            "contains_source_paths": False,
        },
    }


def run_pipeline(
    *,
    config_path: str | Path | None = None,
    profile: str | None = None,
    include_private_paths: bool = False,
) -> dict[str, object]:
    config = load_pipeline_config(config_path=config_path, profile=profile)
    source_path = resolve_source_path(config)
    output_dir = Path(config.pipeline.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    include_private = include_private_paths or not config.privacy.redact_file_paths
    context = build_context(vault_config_from_app_config(source_path, config))
    warehouse = build_warehouse(context)
    output_path = output_dir / PIPELINE_RUN_FILENAME

    try:
        enrichment_stats = run_unresolved_link_ai_enrichment(
            warehouse,
            config=config,
        )
        warehouse_report = warehouse_summary(warehouse)
    finally:
        warehouse.close()

    doctor_report = run_doctor(
        DoctorOptions(
            vault_path=source_path,
            config_path=config.config_path,
            include_samples=include_private,
        )
    )

    run_report: dict[str, object] = {
        "status": doctor_report["status"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "loaded": config.loaded,
            "profile": profile,
            "path": _display_path(
                config.config_path or DEFAULT_CONFIG_PATH,
                include_private_paths=include_private,
            ),
            "path_redacted": not include_private,
        },
        "source": _source_summary(
            config,
            source_path,
            include_private_paths=include_private,
        ),
        "doctor": _doctor_summary(
            sanitize_report(doctor_report, include_private_paths=include_private)
        ),
        "warehouse": warehouse_report,
        "privacy": privacy_posture(
            config,
            include_private_paths=include_private,
            output_path=output_path,
            enrichment_stats=enrichment_stats,
        ),
        "ai": ai_posture(config, enrichment_stats),
        "review": review_summary(warehouse_report),
        "suggestion_counts": suggestion_counts(warehouse_report),
    }

    output_path.write_text(
        json.dumps(run_report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    run_report["output_path"] = str(output_path)
    return run_report


def run_pipeline_doctor(
    *,
    config_path: str | Path | None = None,
    profile: str | None = None,
    strict: bool = False,
    include_private_paths: bool = False,
) -> dict[str, object]:
    config = load_pipeline_config(config_path=config_path, profile=profile)
    source_path = resolve_source_path(config)
    include_private = include_private_paths or not config.privacy.redact_file_paths
    report = run_doctor(
        DoctorOptions(
            vault_path=source_path,
            strict=strict,
            config_path=config.config_path,
            include_samples=include_private,
        )
    )
    return sanitize_report(report, include_private_paths=include_private)
