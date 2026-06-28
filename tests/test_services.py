from __future__ import annotations

from pathlib import Path

import pytest

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
