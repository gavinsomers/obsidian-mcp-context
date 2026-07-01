from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib

from obsidian_mcp_context.domain import NON_ENTITY_NOTE_TYPES
from obsidian_mcp_context.vault import (
    DEFAULT_EXCLUDE_GLOBS,
    DEFAULT_INCLUDE_GLOBS,
    DEFAULT_SOURCE_EXTENSIONS,
    VaultConfig,
)


DEFAULT_CONFIG_PATH = Path(".obsidian-mcp-context.toml")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "examples" / "vault-profiles"
VAULT_PROFILE_ENV = "OBSIDIAN_MCP_VAULT_PROFILE"
DOCTOR_DIAGNOSTIC_MODES = ("warn", "ignore", "error")
SOURCE_TYPES = ("sample", "obsidian")
AI_PROVIDERS = ("none", "mock", "ollama", "openai", "anthropic", "vllm")
HOSTED_AI_PROVIDERS = {"openai", "anthropic"}
DEFAULT_REPLAY_QA_ENTITY_TYPE_PREFERENCES = ("project", "person", "company")
DEFAULT_REPLAY_QA_DECISION_WORDS = ("decision", "decisions", "decided")
DEFAULT_REPLAY_QA_RISK_WORDS = ("risk", "risks", "blocker", "blockers")
DEFAULT_REPLAY_QA_OPEN_LOOP_WORDS = (
    "open",
    "loop",
    "loops",
    "todo",
    "task",
    "tasks",
    "followup",
    "follow-up",
)
DEFAULT_REPLAY_QA_TIMELINE_WORDS = ("timeline", "history", "when", "sequence")


@dataclass(frozen=True)
class SourceConfig:
    type: str = "sample"
    sample_name: str = "synthetic-vault"
    vault_path: str = ""


@dataclass(frozen=True)
class PipelineConfig:
    output_dir: str = "var"
    run_mode: str = "local"


@dataclass(frozen=True)
class PrivacyConfig:
    allow_raw_text_to_ai: bool = False
    allow_hosted_ai: bool = False
    max_context_chars: int = 1500
    redact_file_paths: bool = True


@dataclass(frozen=True)
class AIConfig:
    enabled: bool = False
    provider: str = "none"
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""


@dataclass(frozen=True)
class AppConfig:
    source: SourceConfig = field(default_factory=SourceConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    include_globs: tuple[str, ...] = DEFAULT_INCLUDE_GLOBS
    exclude_globs: tuple[str, ...] = DEFAULT_EXCLUDE_GLOBS
    source_extensions: tuple[str, ...] = DEFAULT_SOURCE_EXTENSIONS
    folder_note_types: dict[str, str] = field(default_factory=dict)
    non_entity_note_types: tuple[str, ...] = tuple(sorted(NON_ENTITY_NOTE_TYPES))
    doctor_lifecycle_metadata: str = "warn"
    doctor_ignored_files: str = "warn"
    doctor_unsupported_files: str = "warn"
    doctor_empty_notes: str = "warn"
    doctor_notes_without_blocks: str = "warn"
    doctor_large_notes: str = "warn"
    doctor_unresolved_wikilinks: str = "warn"
    doctor_unresolved_wikilink_ignore_target_globs: tuple[str, ...] = ()
    replay_qa_entity_type_preferences: tuple[str, ...] = (
        DEFAULT_REPLAY_QA_ENTITY_TYPE_PREFERENCES
    )
    replay_qa_decision_words: tuple[str, ...] = DEFAULT_REPLAY_QA_DECISION_WORDS
    replay_qa_risk_words: tuple[str, ...] = DEFAULT_REPLAY_QA_RISK_WORDS
    replay_qa_open_loop_words: tuple[str, ...] = DEFAULT_REPLAY_QA_OPEN_LOOP_WORDS
    replay_qa_timeline_words: tuple[str, ...] = DEFAULT_REPLAY_QA_TIMELINE_WORDS
    config_path: Path | None = None
    profile_path: Path | None = None
    loaded: bool = False


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return tuple(item for item in value if item)


def _normalized_word_tuple(value: object, field_name: str) -> tuple[str, ...]:
    return tuple(
        word.strip().casefold()
        for word in _string_tuple(value, field_name)
        if word.strip()
    )


def _string_mapping(value: object, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError(f"{field_name} must be a table of string keys and values")
    return {key: item for key, item in value.items() if key and item}


def _choice(value: object, field_name: str, allowed: tuple[str, ...], default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(allowed)
        raise ValueError(f"{field_name} must be one of: {allowed_values}")
    return normalized


def _string(value: object, field_name: str, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def _bool(value: object, field_name: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _positive_int(value: object, field_name: str, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return value


def _table(data: dict[str, object], table_name: str) -> dict[str, object]:
    value = data.get(table_name, {})
    if not isinstance(value, dict):
        raise ValueError(f"{table_name} must be a TOML table")
    return value


def _env_bool(value: str, env_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{env_name} must be a boolean value")


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    source = config.source
    ai = config.ai

    if "OBSIDIAN_MCP_SOURCE_TYPE" in os.environ:
        source = SourceConfig(
            type=_choice(
                os.environ["OBSIDIAN_MCP_SOURCE_TYPE"],
                "OBSIDIAN_MCP_SOURCE_TYPE",
                SOURCE_TYPES,
                source.type,
            ),
            sample_name=source.sample_name,
            vault_path=source.vault_path,
        )

    if "OBSIDIAN_MCP_AI_ENABLED" in os.environ:
        ai = AIConfig(
            enabled=_env_bool(
                os.environ["OBSIDIAN_MCP_AI_ENABLED"],
                "OBSIDIAN_MCP_AI_ENABLED",
            ),
            provider=ai.provider,
            model=ai.model,
            base_url=ai.base_url,
            api_key_env=ai.api_key_env,
        )
    if "OBSIDIAN_MCP_AI_PROVIDER" in os.environ:
        ai = AIConfig(
            enabled=ai.enabled,
            provider=_choice(
                os.environ["OBSIDIAN_MCP_AI_PROVIDER"],
                "OBSIDIAN_MCP_AI_PROVIDER",
                AI_PROVIDERS,
                ai.provider,
            ),
            model=ai.model,
            base_url=ai.base_url,
            api_key_env=ai.api_key_env,
        )
    if "OBSIDIAN_MCP_AI_MODEL" in os.environ:
        ai = AIConfig(
            enabled=ai.enabled,
            provider=ai.provider,
            model=os.environ["OBSIDIAN_MCP_AI_MODEL"].strip(),
            base_url=ai.base_url,
            api_key_env=ai.api_key_env,
        )
    if "OBSIDIAN_MCP_AI_BASE_URL" in os.environ:
        ai = AIConfig(
            enabled=ai.enabled,
            provider=ai.provider,
            model=ai.model,
            base_url=os.environ["OBSIDIAN_MCP_AI_BASE_URL"].strip(),
            api_key_env=ai.api_key_env,
        )
    if "OBSIDIAN_MCP_AI_API_KEY_ENV" in os.environ:
        ai = AIConfig(
            enabled=ai.enabled,
            provider=ai.provider,
            model=ai.model,
            base_url=ai.base_url,
            api_key_env=os.environ["OBSIDIAN_MCP_AI_API_KEY_ENV"].strip(),
        )

    return _validate_app_config(
        AppConfig(
            source=source,
            pipeline=config.pipeline,
            privacy=config.privacy,
            ai=ai,
            include_globs=config.include_globs,
            exclude_globs=config.exclude_globs,
            source_extensions=config.source_extensions,
            folder_note_types=config.folder_note_types,
            non_entity_note_types=config.non_entity_note_types,
            doctor_lifecycle_metadata=config.doctor_lifecycle_metadata,
            doctor_ignored_files=config.doctor_ignored_files,
            doctor_unsupported_files=config.doctor_unsupported_files,
            doctor_empty_notes=config.doctor_empty_notes,
            doctor_notes_without_blocks=config.doctor_notes_without_blocks,
            doctor_large_notes=config.doctor_large_notes,
            doctor_unresolved_wikilinks=config.doctor_unresolved_wikilinks,
            doctor_unresolved_wikilink_ignore_target_globs=(
                config.doctor_unresolved_wikilink_ignore_target_globs
            ),
            replay_qa_entity_type_preferences=config.replay_qa_entity_type_preferences,
            replay_qa_decision_words=config.replay_qa_decision_words,
            replay_qa_risk_words=config.replay_qa_risk_words,
            replay_qa_open_loop_words=config.replay_qa_open_loop_words,
            replay_qa_timeline_words=config.replay_qa_timeline_words,
            config_path=config.config_path,
            profile_path=config.profile_path,
            loaded=config.loaded,
        )
    )


def _validate_app_config(config: AppConfig) -> AppConfig:
    if config.source.type == "sample" and not config.source.sample_name:
        raise ValueError("source.sample_name is required when source.type is sample")
    if config.source.type == "obsidian" and not config.source.vault_path:
        raise ValueError("source.vault_path is required when source.type is obsidian")

    if config.ai.enabled and config.ai.provider == "none":
        raise ValueError("ai.provider must not be none when ai.enabled is true")
    if config.ai.enabled and config.ai.provider in HOSTED_AI_PROVIDERS:
        if not config.privacy.allow_hosted_ai:
            raise ValueError(
                "privacy.allow_hosted_ai must be true to enable hosted AI providers"
            )
        if not config.ai.api_key_env:
            raise ValueError("ai.api_key_env is required for hosted AI providers")
    if config.ai.api_key_env and "=" in config.ai.api_key_env:
        raise ValueError("ai.api_key_env must be an environment variable name, not a key")
    return config


def _load_pipeline_config(data: dict[str, object]) -> tuple[
    SourceConfig,
    PipelineConfig,
    PrivacyConfig,
    AIConfig,
]:
    source_table = _table(data, "source")
    pipeline_table = _table(data, "pipeline")
    privacy_table = _table(data, "privacy")
    ai_table = _table(data, "ai")

    source = SourceConfig(
        type=_choice(source_table.get("type"), "source.type", SOURCE_TYPES, "sample"),
        sample_name=_string(
            source_table.get("sample_name"), "source.sample_name", "synthetic-vault"
        ),
        vault_path=_string(source_table.get("vault_path"), "source.vault_path"),
    )
    pipeline = PipelineConfig(
        output_dir=_string(pipeline_table.get("output_dir"), "pipeline.output_dir", "var"),
        run_mode=_string(pipeline_table.get("run_mode"), "pipeline.run_mode", "local"),
    )
    privacy = PrivacyConfig(
        allow_raw_text_to_ai=_bool(
            privacy_table.get("allow_raw_text_to_ai"),
            "privacy.allow_raw_text_to_ai",
        ),
        allow_hosted_ai=_bool(
            privacy_table.get("allow_hosted_ai"), "privacy.allow_hosted_ai"
        ),
        max_context_chars=_positive_int(
            privacy_table.get("max_context_chars"),
            "privacy.max_context_chars",
            1500,
        ),
        redact_file_paths=_bool(
            privacy_table.get("redact_file_paths"),
            "privacy.redact_file_paths",
            True,
        ),
    )
    ai = AIConfig(
        enabled=_bool(ai_table.get("enabled"), "ai.enabled"),
        provider=_choice(ai_table.get("provider"), "ai.provider", AI_PROVIDERS, "none"),
        model=_string(ai_table.get("model"), "ai.model"),
        base_url=_string(ai_table.get("base_url"), "ai.base_url"),
        api_key_env=_string(ai_table.get("api_key_env"), "ai.api_key_env"),
    )
    return source, pipeline, privacy, ai


def _unresolved_wikilink_config(value: object) -> tuple[str, tuple[str, ...]]:
    if value is None or isinstance(value, str):
        return (
            _choice(value, "doctor.unresolved_wikilinks", DOCTOR_DIAGNOSTIC_MODES, "warn"),
            (),
        )
    if not isinstance(value, dict):
        raise ValueError("doctor.unresolved_wikilinks must be a string or TOML table")
    mode = _choice(
        value.get("mode"),
        "doctor.unresolved_wikilinks.mode",
        DOCTOR_DIAGNOSTIC_MODES,
        "warn",
    )
    ignore_target_globs = _string_tuple(
        value.get("ignore_target_globs"),
        "doctor.unresolved_wikilinks.ignore_target_globs",
    )
    return mode, ignore_target_globs


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def resolve_profile_path(profile_path: str | Path | None = None) -> Path | None:
    value = profile_path or os.environ.get(VAULT_PROFILE_ENV)
    if not value:
        return None
    path = Path(value).expanduser()
    if path.exists() or path.suffix or path.is_absolute() or len(path.parts) > 1:
        return path
    return DEFAULT_PROFILE_DIR / f"{path}.toml"


def _load_toml_file(path: Path, *, label: str) -> dict[str, object]:
    if not path.exists():
        raise ValueError(f"{label} does not exist: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must contain TOML tables: {path}")
    return data


def load_app_config(
    config_path: str | Path | None = None,
    *,
    profile_path: str | Path | None = None,
) -> AppConfig:
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH
    profile = resolve_profile_path(profile_path)
    data: dict[str, object] = {}
    loaded = False

    if profile:
        data = _load_toml_file(profile, label="Vault profile")
        loaded = True

    if path.exists():
        data = _deep_merge(data, _load_toml_file(path, label="Config file"))
        loaded = True
    elif not loaded:
        return _apply_env_overrides(
            AppConfig(config_path=path, profile_path=profile, loaded=False)
        )

    source, pipeline, privacy, ai = _load_pipeline_config(data)
    scan = _table(data, "scan")
    entities = _table(data, "entities")
    doctor = _table(data, "doctor")
    replay_qa = _table(data, "replay_qa")
    replay_qa_intent_words = replay_qa.get("intent_words", {})
    if not isinstance(replay_qa_intent_words, dict):
        raise ValueError("replay_qa.intent_words must be a TOML table")

    include_globs = _string_tuple(scan.get("include_globs"), "scan.include_globs")
    exclude_globs = _string_tuple(scan.get("exclude_globs"), "scan.exclude_globs")
    extra_exclude_globs = _string_tuple(
        scan.get("extra_exclude_globs"), "scan.extra_exclude_globs"
    )
    source_extensions = _string_tuple(
        scan.get("source_extensions"), "scan.source_extensions"
    )

    folder_note_types = _string_mapping(
        entities.get("folders"), "entities.folders"
    )
    non_entity_note_types = _string_tuple(
        entities.get("non_entity_note_types"), "entities.non_entity_note_types"
    )
    replay_qa_entity_type_preferences = tuple(
        entity_type.strip().lower()
        for entity_type in _string_tuple(
            replay_qa.get("entity_type_preferences"),
            "replay_qa.entity_type_preferences",
        )
        if entity_type.strip()
    )
    replay_qa_decision_words = _normalized_word_tuple(
        replay_qa_intent_words.get("decisions"),
        "replay_qa.intent_words.decisions",
    )
    replay_qa_risk_words = _normalized_word_tuple(
        replay_qa_intent_words.get("risks"),
        "replay_qa.intent_words.risks",
    )
    replay_qa_open_loop_words = _normalized_word_tuple(
        replay_qa_intent_words.get("open_loops"),
        "replay_qa.intent_words.open_loops",
    )
    replay_qa_timeline_words = _normalized_word_tuple(
        replay_qa_intent_words.get("timeline"),
        "replay_qa.intent_words.timeline",
    )
    doctor_lifecycle_metadata = _choice(
        doctor.get("lifecycle_metadata"),
        "doctor.lifecycle_metadata",
        DOCTOR_DIAGNOSTIC_MODES,
        "warn",
    )
    doctor_ignored_files = _choice(
        doctor.get("ignored_files"),
        "doctor.ignored_files",
        DOCTOR_DIAGNOSTIC_MODES,
        "warn",
    )
    doctor_unsupported_files = _choice(
        doctor.get("unsupported_files"),
        "doctor.unsupported_files",
        DOCTOR_DIAGNOSTIC_MODES,
        "warn",
    )
    doctor_empty_notes = _choice(
        doctor.get("empty_notes"),
        "doctor.empty_notes",
        DOCTOR_DIAGNOSTIC_MODES,
        "warn",
    )
    doctor_notes_without_blocks = _choice(
        doctor.get("notes_without_blocks"),
        "doctor.notes_without_blocks",
        DOCTOR_DIAGNOSTIC_MODES,
        "warn",
    )
    doctor_large_notes = _choice(
        doctor.get("large_notes"),
        "doctor.large_notes",
        DOCTOR_DIAGNOSTIC_MODES,
        "warn",
    )
    (
        doctor_unresolved_wikilinks,
        doctor_unresolved_wikilink_ignore_target_globs,
    ) = _unresolved_wikilink_config(
        doctor.get("unresolved_wikilinks"),
    )

    return _apply_env_overrides(AppConfig(
        source=source,
        pipeline=pipeline,
        privacy=privacy,
        ai=ai,
        include_globs=include_globs or DEFAULT_INCLUDE_GLOBS,
        exclude_globs=(exclude_globs or DEFAULT_EXCLUDE_GLOBS) + extra_exclude_globs,
        source_extensions=source_extensions or DEFAULT_SOURCE_EXTENSIONS,
        folder_note_types=folder_note_types,
        non_entity_note_types=non_entity_note_types or tuple(sorted(NON_ENTITY_NOTE_TYPES)),
        doctor_lifecycle_metadata=doctor_lifecycle_metadata,
        doctor_ignored_files=doctor_ignored_files,
        doctor_unsupported_files=doctor_unsupported_files,
        doctor_empty_notes=doctor_empty_notes,
        doctor_notes_without_blocks=doctor_notes_without_blocks,
        doctor_large_notes=doctor_large_notes,
        doctor_unresolved_wikilinks=doctor_unresolved_wikilinks,
        doctor_unresolved_wikilink_ignore_target_globs=(
            doctor_unresolved_wikilink_ignore_target_globs
        ),
        replay_qa_entity_type_preferences=(
            replay_qa_entity_type_preferences
            or DEFAULT_REPLAY_QA_ENTITY_TYPE_PREFERENCES
        ),
        replay_qa_decision_words=(
            replay_qa_decision_words or DEFAULT_REPLAY_QA_DECISION_WORDS
        ),
        replay_qa_risk_words=(replay_qa_risk_words or DEFAULT_REPLAY_QA_RISK_WORDS),
        replay_qa_open_loop_words=(
            replay_qa_open_loop_words or DEFAULT_REPLAY_QA_OPEN_LOOP_WORDS
        ),
        replay_qa_timeline_words=(
            replay_qa_timeline_words or DEFAULT_REPLAY_QA_TIMELINE_WORDS
        ),
        config_path=path,
        profile_path=profile,
        loaded=loaded,
    ))


def vault_config_from_app_config(vault_path: str | Path, config: AppConfig) -> VaultConfig:
    return VaultConfig(
        vault_path=Path(vault_path),
        include_globs=config.include_globs,
        exclude_globs=config.exclude_globs,
        source_extensions=config.source_extensions,
        folder_note_types=config.folder_note_types,
        non_entity_note_types=config.non_entity_note_types,
    )
