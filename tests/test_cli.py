from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_mcp_context.cli import main


def test_cli_modeled_command_warns_on_direct_parse_fallback(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Project Atlas.md").write_text("# Project Atlas\n", encoding="utf-8")

    result = main(["--vault", str(vault), "entities"])

    captured = capsys.readouterr()
    assert result == 0
    assert "no valid Postgres/dbt warehouse" in captured.err
    assert "falling back to direct parser diagnostics" in captured.err


def test_cli_doctor_accepts_vault_profile(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    profile_path = tmp_path / "profile.toml"
    (vault / "Accounts").mkdir(parents=True)
    (vault / "Accounts" / "Acme.md").write_text("# Acme\n", encoding="utf-8")
    profile_path.write_text(
        """
[entities.folders]
Accounts = "account"

[doctor]
lifecycle_metadata = "ignore"
""".strip(),
        encoding="utf-8",
    )

    result = main(
        [
            "--vault",
            str(vault),
            "--vault-profile",
            str(profile_path),
            "doctor",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert str(profile_path) in captured.out


def test_cli_lists_context_presets_without_vault(capsys):
    result = main(["context-presets"])

    captured = capsys.readouterr()
    assert result == 0
    assert '"name": "entity_brief"' in captured.out
    assert '"name": "stale_entities"' in captured.out


def test_cli_context_preset_validates_required_entity_type(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--vault",
                str(vault),
                "context-preset",
                "entity_brief",
                "--entity",
                "Acme",
            ]
        )

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "entity_brief requires --entity-type" in captured.err
