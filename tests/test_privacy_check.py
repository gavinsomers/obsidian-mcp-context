from pathlib import Path
import shutil
import subprocess

import pytest


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git executable is required for privacy check integration tests",
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def test_privacy_check_blocks_local_sensitive_terms(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copy2("scripts/privacy_check.sh", scripts / "privacy_check.sh")
    (repo / ".privacy-banned-terms.local").write_text("PersonalVault\n", encoding="utf-8")
    (repo / "notes.md").write_text("Path: /tmp/PersonalVault\n", encoding="utf-8")
    _git(repo, "add", "notes.md")

    result = subprocess.run(
        ["bash", "scripts/privacy_check.sh"],
        cwd=repo,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "PersonalVault" in result.stderr


def test_privacy_check_passes_without_staged_sensitive_terms(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copy2("scripts/privacy_check.sh", scripts / "privacy_check.sh")
    (repo / "notes.md").write_text("Safe fixture content.\n", encoding="utf-8")
    _git(repo, "add", "notes.md")

    result = subprocess.run(
        ["bash", "scripts/privacy_check.sh"],
        cwd=repo,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Privacy check passed." in result.stdout


def test_privacy_check_all_blocks_tracked_runtime_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copy2("scripts/privacy_check.sh", scripts / "privacy_check.sh")
    (repo / "var").mkdir()
    (repo / "var" / "warehouse.duckdb").write_text("runtime output\n", encoding="utf-8")
    _git(repo, "add", "var/warehouse.duckdb")

    result = subprocess.run(
        ["bash", "scripts/privacy_check.sh", "--all"],
        cwd=repo,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "var/warehouse.duckdb" in result.stderr


def test_privacy_check_all_blocks_tracked_local_sensitive_terms(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copy2("scripts/privacy_check.sh", scripts / "privacy_check.sh")
    (repo / ".privacy-banned-terms.local").write_text("PersonalVault\n", encoding="utf-8")
    (repo / "docs.md").write_text("Do not publish PersonalVault paths.\n", encoding="utf-8")
    _git(repo, "add", "docs.md")

    result = subprocess.run(
        ["bash", "scripts/privacy_check.sh", "--all"],
        cwd=repo,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "PersonalVault" in result.stderr
