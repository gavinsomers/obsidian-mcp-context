from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_mcp_context import postgres_warehouse
from obsidian_mcp_context.config import load_app_config
from obsidian_mcp_context.security import VaultPathError
from obsidian_mcp_context.services import ContextService
from obsidian_mcp_context.vault import VaultConfig, build_context


def test_allowed_roots_reject_vault_paths_outside_configured_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    allowed = tmp_path / "allowed"
    blocked = tmp_path / "blocked"
    allowed.mkdir()
    blocked.mkdir()
    monkeypatch.setenv("OBSIDIAN_MCP_ALLOWED_ROOTS", str(allowed))

    with pytest.raises(VaultPathError):
        build_context(VaultConfig(vault_path=blocked))


def test_context_service_refreshes_cache_when_note_changes(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "Note.md"
    note.write_text("# Note\n\nFirst version\n", encoding="utf-8")
    service = ContextService()

    first = service.search_blocks(vault, text="First version")
    assert first

    note.write_text("# Note\n\nSecond version\n", encoding="utf-8")
    second = service.search_blocks(vault, text="Second version")

    assert second
    assert service.search_blocks(vault, text="First version") == []


def test_context_service_selects_postgres_reader_when_configured(
    monkeypatch: pytest.MonkeyPatch,
):
    service = ContextService()
    monkeypatch.setenv("WAREHOUSE_BACKEND", "postgres")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://example")
    monkeypatch.setattr(postgres_warehouse, "is_available", lambda dsn: True)

    reader = service.dbt_reader()

    assert reader == (postgres_warehouse, "postgresql://example")


def test_context_service_does_not_select_unavailable_postgres_reader(
    monkeypatch: pytest.MonkeyPatch,
):
    service = ContextService()
    monkeypatch.setenv("WAREHOUSE_BACKEND", "postgres")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://example")
    monkeypatch.setattr(postgres_warehouse, "is_available", lambda dsn: False)

    assert service.dbt_reader() is None


def test_context_service_raises_in_explicit_postgres_mode_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    service = ContextService()
    monkeypatch.setenv("WAREHOUSE_BACKEND", "postgres")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://example")
    monkeypatch.setattr(postgres_warehouse, "is_available", lambda dsn: False)

    with pytest.raises(RuntimeError, match="WAREHOUSE_BACKEND=postgres"):
        service.warehouse_summary(tmp_path)


def test_context_service_recent_context_does_not_parse_in_explicit_postgres_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    service = ContextService()
    monkeypatch.setenv("WAREHOUSE_BACKEND", "postgres")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://example")
    monkeypatch.setattr(postgres_warehouse, "is_available", lambda dsn: False)

    with pytest.raises(RuntimeError, match="WAREHOUSE_BACKEND=postgres"):
        service.context_preset(tmp_path, "recent_context", limit=3)


class FakePresetWarehouse:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def entity_context(
        self,
        handle: str,
        entity_type: str,
        entity: str,
        limit: int,
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                "entity_context",
                {"entity_type": entity_type, "entity": entity, "limit": limit},
            )
        )
        return [{"entity_type": entity_type, "entity_name": entity}]


class FakeProfileWarehouse:
    def list_vault_profiles(self, handle: str, limit: int) -> list[dict[str, object]]:
        return [
            {
                "vault_profile_id": "profile_123",
                "profile_loaded": True,
                "source_file_count": 42,
                "limit": limit,
            }
        ]

    def list_entity_open_loops(
        self,
        handle: str,
        entity_type: str | None,
        entity: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                "list_entity_open_loops",
                {"entity_type": entity_type, "entity": entity, "limit": limit},
            )
        )
        return [{"entity_type": entity_type, "entity_name": entity}]


def test_context_service_lists_agent_ready_presets():
    service = ContextService()

    presets = {preset["name"]: preset for preset in service.context_presets()}

    assert "entity_brief" in presets
    assert presets["entity_brief"]["requires_entity"] is True
    assert presets["entity_brief"]["requires_entity_type"] is True
    assert "stale_entities" in presets


def test_context_service_context_preset_dispatches_to_mart_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    service = ContextService()
    fake_warehouse = FakePresetWarehouse()
    monkeypatch.setattr(
        service,
        "dbt_reader",
        lambda postgres_dsn=None: (fake_warehouse, "postgresql://example"),
    )

    result = service.context_preset(
        tmp_path,
        "entity_brief",
        entity_type="account",
        entity="Acme",
        limit=3,
    )

    assert result["mode"] == "mart-backed"
    assert result["row_count"] == 1
    assert result["warning"] is None
    assert fake_warehouse.calls == [
        (
            "entity_context",
            {"entity_type": "account", "entity": "Acme", "limit": 3},
        )
    ]


def test_context_service_context_preset_reports_mart_requirement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    service = ContextService()
    monkeypatch.setattr(service, "dbt_reader", lambda postgres_dsn=None: None)

    result = service.context_preset(tmp_path, "decision_log", limit=3)

    assert result["mode"] == "parser-diagnostic"
    assert result["rows"] == []
    assert result["warning"] == "Preset requires a valid Postgres/dbt mart warehouse."


def test_context_service_profile_metadata_redacts_local_paths(tmp_path: Path):
    vault = tmp_path / "vault"
    profile_path = tmp_path / "profile.toml"
    (vault / "Accounts").mkdir(parents=True)
    (vault / "Accounts" / "Acme.md").write_text("# Acme\n", encoding="utf-8")
    profile_path.write_text(
        """
[entities.folders]
Accounts = "account"
""".strip(),
        encoding="utf-8",
    )
    app_config = load_app_config(
        config_path=tmp_path / "missing.toml",
        profile_path=profile_path,
    )
    service = ContextService(app_config=app_config)

    result = service.vault_profile_metadata(vault)
    profile = result["profiles"][0]

    assert result["mode"] == "parser-diagnostic"
    assert profile["profile_loaded"] is True
    assert profile["profile_ref"] == "<redacted:profile.toml>"
    assert profile["folder_note_types"] == {"Accounts": "account"}
    assert profile["note_type_counts"] == {"account": 1}
    assert profile["source_file_count"] == 1
    assert str(tmp_path) not in str(result)


def test_context_service_profile_metadata_uses_mart_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    service = ContextService()
    fake_warehouse = FakeProfileWarehouse()
    monkeypatch.setattr(
        service,
        "dbt_reader",
        lambda postgres_dsn=None: (fake_warehouse, "postgresql://example"),
    )

    result = service.vault_profile_metadata(tmp_path, limit=3)

    assert result == {
        "mode": "mart-backed",
        "row_count": 1,
        "profiles": [
            {
                "vault_profile_id": "profile_123",
                "profile_loaded": True,
                "source_file_count": 42,
                "limit": 3,
            }
        ],
    }
