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
        ["bash", SCRIPT, "--with-inspection"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Unknown option: --with-inspection" in result.stderr


def test_dataset_workflow_script_rejects_missing_manifest_before_docker(tmp_path):
    vault = tmp_path / "generated-current"
    vault.mkdir()
    (vault / "Projects").mkdir()
    (vault / "Projects" / "Project Atlas.md").write_text("# Project Atlas\n", encoding="utf-8")

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

