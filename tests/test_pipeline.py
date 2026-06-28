from __future__ import annotations

import json
from pathlib import Path

from obsidian_mcp_context.cli import main
from obsidian_mcp_context.pipeline import (
    PipelineConfigError,
    load_pipeline_config,
    resolve_source_path,
    run_pipeline,
)


def test_pipeline_run_writes_runtime_report_without_mutating_config(tmp_path: Path):
    output_dir = tmp_path / "var"
    config_path = tmp_path / "config.toml"
    config_text = f"""
[source]
type = "sample"
sample_name = "minimal-vault"

[pipeline]
output_dir = "{output_dir}"
warehouse_path = "{output_dir / "warehouse.duckdb"}"

[doctor]
lifecycle_metadata = "ignore"
""".strip()
    config_path.write_text(config_text, encoding="utf-8")

    report = run_pipeline(config_path=config_path)

    output_path = output_dir / "pipeline-run.json"
    assert output_path.exists()
    assert config_path.read_text(encoding="utf-8") == config_text
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] in {"ok", "warning"}
    assert payload["source"] == {
        "type": "sample",
        "exists": True,
        "path": "[redacted]",
        "path_redacted": True,
        "sample_name": "minimal-vault",
    }
    assert payload["ai"]["enabled"] is False
    assert payload["ai"]["calls"] == 0
    assert payload["suggestion_counts"] == {
        "deterministic_suggested_links": 0,
        "ai_suggested_links": 0,
        "ai_related_notes": 0,
        "ai_entity_alias_suggestions": 0,
    }
    assert report["output_path"] == str(output_path)


def test_pipeline_run_redacts_local_obsidian_paths_by_default(tmp_path: Path):
    vault = tmp_path / "private-vault"
    output_dir = tmp_path / "var"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[source]
type = "obsidian"
vault_path = "{vault}"

[pipeline]
output_dir = "{output_dir}"

[doctor]
lifecycle_metadata = "ignore"
""".strip(),
        encoding="utf-8",
    )

    run_pipeline(config_path=config_path)

    payload_text = (output_dir / "pipeline-run.json").read_text(encoding="utf-8")
    assert str(vault) not in payload_text
    assert str(config_path) not in payload_text
    payload = json.loads(payload_text)
    assert payload["source"]["path"] == "[redacted]"
    assert payload["doctor"]["warehouse"]["in_memory"]["ok"] is True


def test_pipeline_run_can_include_private_paths_when_explicitly_requested(tmp_path: Path):
    vault = tmp_path / "private-vault"
    output_dir = tmp_path / "var"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[source]
type = "obsidian"
vault_path = "{vault}"

[pipeline]
output_dir = "{output_dir}"

[doctor]
lifecycle_metadata = "ignore"
""".strip(),
        encoding="utf-8",
    )

    run_pipeline(config_path=config_path, include_private_paths=True)

    payload_text = (output_dir / "pipeline-run.json").read_text(encoding="utf-8")
    assert str(vault) in payload_text
    assert str(config_path) in payload_text


def test_pipeline_profile_sample_resolves_example_vault():
    config = load_pipeline_config(profile="sample")

    source_path = resolve_source_path(config)

    assert source_path.name == "synthetic-vault"
    assert source_path.exists()


def test_pipeline_rejects_google_drive_source_for_now(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[source]
type = "google_drive"
""".strip(),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path=config_path)

    try:
        resolve_source_path(config)
    except PipelineConfigError as exc:
        assert "google_drive is not implemented" in str(exc)
    else:
        raise AssertionError("Expected google_drive source to fail cleanly")


def test_pipeline_cli_run_accepts_config_without_global_vault(tmp_path: Path):
    output_dir = tmp_path / "var"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[source]
type = "sample"
sample_name = "minimal-vault"

[pipeline]
output_dir = "{output_dir}"

[doctor]
lifecycle_metadata = "ignore"
""".strip(),
        encoding="utf-8",
    )

    result = main(["pipeline", "run", "--config", str(config_path)])

    assert result == 0
    assert (output_dir / "pipeline-run.json").exists()


def test_pipeline_run_reports_deterministic_suggestion_counts(tmp_path: Path):
    vault = tmp_path / "vault"
    output_dir = tmp_path / "var"
    (vault / "Projects").mkdir(parents=True)
    (vault / "Daily").mkdir()
    (vault / "Projects" / "Project Atlas.md").write_text(
        "# Project Atlas\n", encoding="utf-8"
    )
    (vault / "Daily" / "2026-06-28.md").write_text(
        "# Daily\n\n[[Project Atals]]\n", encoding="utf-8"
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[source]
type = "obsidian"
vault_path = "{vault}"

[pipeline]
output_dir = "{output_dir}"

[doctor]
lifecycle_metadata = "ignore"
""".strip(),
        encoding="utf-8",
    )

    run_pipeline(config_path=config_path)

    payload = json.loads((output_dir / "pipeline-run.json").read_text(encoding="utf-8"))
    assert payload["suggestion_counts"]["deterministic_suggested_links"] >= 1
    assert (
        payload["warehouse"]["tables"]["deterministic_suggested_links"]
        == payload["suggestion_counts"]["deterministic_suggested_links"]
    )
