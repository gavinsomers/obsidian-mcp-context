from __future__ import annotations

from pathlib import Path
import subprocess


SCRIPT = "scripts/run_dataset_workflow.sh"


def test_dataset_workflow_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", SCRIPT],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr


def test_dataset_workflow_script_prints_help_without_starting_services():
    result = subprocess.run(
        ["bash", SCRIPT, "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "run_dataset_workflow.sh" in result.stdout
    assert "small|medium|large|synthetic" in result.stdout
    assert "start the MCP server" in result.stdout
    assert "--with-dbt-docs" in result.stdout
    assert "--with-table-browser" in result.stdout
    assert "--with-inspection" in result.stdout


def test_dataset_workflow_script_requires_dataset_argument():
    result = subprocess.run(
        ["bash", SCRIPT],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_dataset_workflow_script_rejects_unknown_option_before_docker():
    result = subprocess.run(
        ["bash", SCRIPT, "--unknown"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Unknown option: --unknown" in result.stderr


def test_dataset_workflow_script_rejects_missing_manifest_before_docker(tmp_path):
    vault = tmp_path / "generated-current"
    vault.mkdir()
    (vault / "projects").mkdir()
    (vault / "projects" / "project_atlas.md").write_text("# Project Atlas\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", SCRIPT, str(vault)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Dataset manifest is missing" in result.stderr


def test_dataset_workflow_script_rejects_manifest_without_notes_before_docker(tmp_path):
    vault = tmp_path / "generated-current"
    vault.mkdir()
    (vault / "manifest.json").write_text('{"dataset_id": "empty"}\n', encoding="utf-8")

    result = subprocess.run(
        ["bash", SCRIPT, str(vault)],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Dataset contains no Markdown notes" in result.stderr


def test_dataset_workflow_script_keeps_replay_out_of_default_path():
    script = Path(SCRIPT).read_text(encoding="utf-8")

    assert "replay_loader" not in script
    assert "replay_scheduler" not in script
    assert "replay-dashboard" not in script
    assert "vault-obsidian" not in script
    assert "replay-qa" not in script


def test_dataset_workflow_script_starts_inspection_services_only_behind_flags():
    script = Path(SCRIPT).read_text(encoding="utf-8")

    assert "--with-dbt-docs" in script
    assert "--with-table-browser" in script
    assert "--with-inspection" in script
    assert 'run_logged dbt-docs "${compose[@]}" up -d dbt-docs' in script
    assert (
        'run_logged postgres-browser "${compose[@]}" up -d postgres-browser'
        in script
    )
    assert 'if [[ "$start_dbt_docs" == "1" ]]; then' in script
    assert 'if [[ "$start_table_browser" == "1" ]]; then' in script
