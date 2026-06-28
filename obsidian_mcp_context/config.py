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


@dataclass(frozen=True)
class AppConfig:
    include_globs: tuple[str, ...] = DEFAULT_INCLUDE_GLOBS
    exclude_globs: tuple[str, ...] = DEFAULT_EXCLUDE_GLOBS
    source_extensions: tuple[str, ...] = DEFAULT_SOURCE_EXTENSIONS
    folder_note_types: dict[str, str] = field(default_factory=dict)
    non_entity_note_types: tuple[str, ...] = tuple(sorted(NON_ENTITY_NOTE_TYPES))
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

    return AppConfig(
        include_globs=include_globs or DEFAULT_INCLUDE_GLOBS,
        exclude_globs=(exclude_globs or DEFAULT_EXCLUDE_GLOBS) + extra_exclude_globs,
        source_extensions=source_extensions or DEFAULT_SOURCE_EXTENSIONS,
        folder_note_types=folder_note_types,
        non_entity_note_types=non_entity_note_types or tuple(sorted(NON_ENTITY_NOTE_TYPES)),
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
