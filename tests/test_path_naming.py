from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


PROTECTED_COMPONENTS = {
    "AGENTS.md",
    "Brewfile",
    "CLAUDE.md",
    "CMakeLists.txt",
    "CODEOWNERS",
    "Dockerfile",
    "GEMINI.md",
    "Gemfile",
    "ISSUE_TEMPLATE",
    "Justfile",
    "Makefile",
    "PULL_REQUEST_TEMPLATE",
    "Pipfile",
    "Pipfile.lock",
    "Procfile",
    "Rakefile",
    "SKILL.md",
    "Vagrantfile",
}


def test_tracked_paths_follow_lowercase_naming_convention():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip("tracked-path check requires a Git worktree")

    offenders: list[str] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = os.fsdecode(raw_path)
        for component in Path(path).parts:
            if component in PROTECTED_COMPONENTS:
                continue
            if any(char.isupper() or char.isspace() for char in component):
                offenders.append(path)
                break

    assert offenders == []
