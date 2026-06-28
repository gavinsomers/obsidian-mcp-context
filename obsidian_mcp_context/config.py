from __future__ import annotations

from dataclasses import dataclass, field
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
DOCTOR_DIAGNOSTIC_MODES = ("warn", "ignore", "error")


@dataclass(frozen=True)
class AppConfig:
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
    config_path: Path | None = None
    loaded: bool = False


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return tuple(item for item in value if item)


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


def load_app_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return AppConfig(config_path=path, loaded=False)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain TOML tables: {path}")

    scan = data.get("scan", {})
    if not isinstance(scan, dict):
        raise ValueError("scan must be a TOML table")
    entities = data.get("entities", {})
    if not isinstance(entities, dict):
        raise ValueError("entities must be a TOML table")
    doctor = data.get("doctor", {})
    if not isinstance(doctor, dict):
        raise ValueError("doctor must be a TOML table")

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

    return AppConfig(
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
        config_path=path,
        loaded=True,
    )


def vault_config_from_app_config(vault_path: str | Path, config: AppConfig) -> VaultConfig:
    return VaultConfig(
        vault_path=Path(vault_path),
        include_globs=config.include_globs,
        exclude_globs=config.exclude_globs,
        source_extensions=config.source_extensions,
        folder_note_types=config.folder_note_types,
        non_entity_note_types=config.non_entity_note_types,
    )
