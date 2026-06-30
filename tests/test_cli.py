from __future__ import annotations

from pathlib import Path

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
