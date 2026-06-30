from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path

from obsidian_mcp_context import postgres_warehouse
from obsidian_mcp_context.query import (
    get_note_context,
    list_notes,
    list_tasks,
    search_blocks,
)
from obsidian_mcp_context.security import validate_vault_path
from obsidian_mcp_context.vault import VaultConfig, VaultContext, build_context, scan_vault
from obsidian_mcp_context.warehouse import (
    agent_context,
    build_warehouse,
    entity_timeline,
    list_entities,
    warehouse_summary,
)


LOGGER = logging.getLogger(__name__)
FALLBACK_WARNING = (
    "No valid dbt warehouse found; falling back to direct parser "
    "diagnostics. Build the warehouse with obsidian-mcp-context-ingest-postgres and dbt "
    "for normal modeled query serving."
)


def split_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class ContextCacheEntry:
    signature: tuple[tuple[str, int, int], ...]
    context: VaultContext


class ContextCache:
    def __init__(self, max_entries: int = 8) -> None:
        self.max_entries = max_entries
        self._entries: dict[tuple[object, ...], ContextCacheEntry] = {}

    def load(self, config: VaultConfig) -> VaultContext:
        resolved_config = VaultConfig(
            vault_path=validate_vault_path(config.vault_path),
            include_globs=config.include_globs,
            exclude_globs=config.exclude_globs,
            source_extensions=config.source_extensions,
            folder_note_types=config.folder_note_types,
            non_entity_note_types=config.non_entity_note_types,
        )
        files = scan_vault(resolved_config)
        signature = tuple(
            (
                source_file.source_path,
                source_file.absolute_path.stat().st_mtime_ns,
                source_file.absolute_path.stat().st_size,
            )
            for source_file in files
        )
        key = (
            str(resolved_config.vault_path),
            resolved_config.include_globs,
            resolved_config.exclude_globs,
            resolved_config.source_extensions,
            tuple(sorted((resolved_config.folder_note_types or {}).items())),
            resolved_config.non_entity_note_types,
        )
        entry = self._entries.get(key)
        if entry and entry.signature == signature:
            return entry.context

        context = build_context(resolved_config)
        if len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = ContextCacheEntry(signature=signature, context=context)
        return context

    def clear(self) -> None:
        self._entries.clear()


class ContextService:
    def __init__(self, cache: ContextCache | None = None) -> None:
        self.cache = cache or ContextCache()

    def vault_config(
        self,
        vault_path: str | Path,
        include_globs: str | None = None,
        exclude_globs: str | None = None,
        source_extensions: str | None = None,
    ) -> VaultConfig:
        return VaultConfig(
            vault_path=validate_vault_path(vault_path),
            include_globs=split_csv(include_globs, VaultConfig.include_globs),
            exclude_globs=split_csv(exclude_globs, VaultConfig.exclude_globs),
            source_extensions=split_csv(source_extensions, VaultConfig.source_extensions),
        )

    def context(
        self,
        vault_path: str | Path,
        include_globs: str | None = None,
        exclude_globs: str | None = None,
        source_extensions: str | None = None,
    ) -> VaultContext:
        return self.cache.load(
            self.vault_config(
                vault_path,
                include_globs=include_globs,
                exclude_globs=exclude_globs,
                source_extensions=source_extensions,
            )
        )

    def dbt_reader(
        self,
        warehouse_path: str | Path | None = None,
    ) -> tuple[object, str | Path] | None:
        postgres_dsn = postgres_warehouse.resolve_postgres_dsn()
        if postgres_dsn and postgres_warehouse.is_available(postgres_dsn):
            return postgres_warehouse, postgres_dsn
        return None

    def list_notes(self, vault_path: str | Path, limit: int) -> list[dict[str, object]]:
        return list_notes(self.context(vault_path), limit=limit)

    def search_blocks(
        self,
        vault_path: str | Path,
        text: str | None = None,
        source_path: str | None = None,
        heading: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, object]]:
        return search_blocks(
            self.context(vault_path),
            text=text,
            source_path=source_path,
            heading=heading,
            limit=limit,
        )

    def list_tasks(
        self,
        vault_path: str | Path,
        checked: bool | None = None,
        text: str | None = None,
        source_path: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        return list_tasks(
            self.context(vault_path),
            checked=checked,
            text=text,
            source_path=source_path,
            limit=limit,
        )

    def note_context(self, vault_path: str | Path, source_path: str) -> dict[str, object]:
        return get_note_context(self.context(vault_path), source_path=source_path)

    def warehouse_summary(
        self,
        vault_path: str | Path,
        warehouse_path: str | Path | None = None,
    ) -> dict[str, object]:
        if reader := self.dbt_reader(warehouse_path):
            warehouse, handle = reader
            return warehouse.summary(handle)
        LOGGER.warning("%s", FALLBACK_WARNING)
        warehouse = build_warehouse(self.context(vault_path))
        summary = warehouse_summary(warehouse)
        summary["warning"] = FALLBACK_WARNING
        summary["warehouse"] = "in_memory_diagnostic"
        return summary

    def list_entities(
        self,
        vault_path: str | Path,
        entity_type: str | None = None,
        text: str | None = None,
        limit: int = 100,
        warehouse_path: str | Path | None = None,
    ) -> list[dict[str, object]]:
        if reader := self.dbt_reader(warehouse_path):
            warehouse, handle = reader
            return warehouse.list_entities(
                handle,
                entity_type=entity_type,
                text=text,
                limit=limit,
            )
        LOGGER.warning("%s", FALLBACK_WARNING)
        warehouse = build_warehouse(self.context(vault_path))
        return list_entities(warehouse, entity_type=entity_type, text=text, limit=limit)

    def entity_types(
        self,
        warehouse_path: str | Path | None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_entity_types(handle, limit=limit)

    def entity(
        self,
        warehouse_path: str | Path | None,
        entity_type: str,
        name: str,
    ) -> dict[str, object]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return {}
        warehouse, handle = reader
        return warehouse.get_entity(handle, entity_type=entity_type, name=name)

    def entity_context_generic(
        self,
        warehouse_path: str | Path | None,
        entity_type: str,
        entity: str,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.entity_context(
            handle,
            entity_type=entity_type,
            entity=entity,
            limit=limit,
        )

    def entity_events(
        self,
        warehouse_path: str | Path | None,
        entity_type: str | None = None,
        entity: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_entity_events(
            handle,
            entity_type=entity_type,
            entity=entity,
            event_type=event_type,
            limit=limit,
        )

    def entity_relationships(
        self,
        warehouse_path: str | Path | None,
        entity_type: str | None = None,
        entity: str | None = None,
        relationship_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_entity_relationships(
            handle,
            entity_type=entity_type,
            entity=entity,
            relationship_type=relationship_type,
            limit=limit,
        )

    def entity_states(
        self,
        warehouse_path: str | Path | None,
        entity_type: str | None = None,
        entity: str | None = None,
        state_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_entity_states(
            handle,
            entity_type=entity_type,
            entity=entity,
            state_type=state_type,
            status=status,
            limit=limit,
        )

    def entity_open_loops(
        self,
        warehouse_path: str | Path | None,
        entity_type: str | None = None,
        entity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_entity_open_loops(
            handle,
            entity_type=entity_type,
            entity=entity,
            limit=limit,
        )

    def entity_timeline(
        self,
        vault_path: str | Path,
        entity: str,
        text: str | None = None,
        limit: int = 50,
        warehouse_path: str | Path | None = None,
    ) -> list[dict[str, object]]:
        if reader := self.dbt_reader(warehouse_path):
            warehouse, handle = reader
            entity_row = self._dbt_entity_row(warehouse, handle, entity)
            if entity_row and entity_row["entity_type"] == "project":
                return warehouse.project_context(
                    handle,
                    project=str(entity_row["name"]),
                    limit=limit,
                )
            if entity_row and entity_row["entity_type"] == "person":
                return warehouse.person_context(
                    handle,
                    person=str(entity_row["name"]),
                    limit=limit,
                )
        LOGGER.warning("%s", FALLBACK_WARNING)
        warehouse = build_warehouse(self.context(vault_path))
        return entity_timeline(warehouse, entity=entity, text=text, limit=limit)

    def agent_context(
        self,
        vault_path: str | Path,
        text: str | None = None,
        entity: str | None = None,
        event_type: str | None = None,
        limit: int = 25,
        warehouse_path: str | Path | None = None,
    ) -> list[dict[str, object]]:
        if reader := self.dbt_reader(warehouse_path):
            warehouse, handle = reader
            if entity:
                entity_row = self._dbt_entity_row(warehouse, handle, entity)
                if entity_row and entity_row["entity_type"] == "project":
                    return warehouse.project_context(
                        handle,
                        project=str(entity_row["name"]),
                        limit=limit,
                    )
                if entity_row and entity_row["entity_type"] == "person":
                    return warehouse.person_context(
                        handle,
                        person=str(entity_row["name"]),
                        limit=limit,
                    )
            if event_type == "open_loop":
                return warehouse.list_open_loops(
                    handle,
                    entity=entity,
                    limit=limit,
                )
        LOGGER.warning("%s", FALLBACK_WARNING)
        warehouse = build_warehouse(self.context(vault_path))
        return agent_context(
            warehouse,
            text=text,
            entity=entity,
            event_type=event_type,
            limit=limit,
        )

    def project_context(
        self,
        warehouse_path: str | Path | None,
        project: str,
        limit: int,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.project_context(handle, project=project, limit=limit)

    def projects(
        self,
        warehouse_path: str | Path | None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_projects(handle, limit=limit)

    def person_context(
        self,
        warehouse_path: str | Path | None,
        person: str,
        limit: int,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.person_context(handle, person=person, limit=limit)

    def people(
        self,
        warehouse_path: str | Path | None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_people(handle, limit=limit)

    def companies(
        self,
        warehouse_path: str | Path | None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_companies(handle, limit=limit)

    def open_loops(
        self,
        warehouse_path: str | Path | None,
        entity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_open_loops(handle, entity=entity, limit=limit)

    def decisions(
        self,
        warehouse_path: str | Path | None,
        entity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_decisions(
            handle,
            entity=entity,
            status=status,
            limit=limit,
        )

    def risks(
        self,
        warehouse_path: str | Path | None,
        entity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not (reader := self.dbt_reader(warehouse_path)):
            return []
        warehouse, handle = reader
        return warehouse.list_risks(
            handle,
            entity=entity,
            status=status,
            limit=limit,
        )

    def _dbt_entity_row(
        self,
        warehouse: object,
        handle: str | Path,
        entity: str,
    ) -> dict[str, object] | None:
        entities = warehouse.list_entities(handle, text=entity, limit=500)
        return next(
            (row for row in entities if str(row["name"]).casefold() == entity.casefold()),
            None,
        )


default_context_service = ContextService()
