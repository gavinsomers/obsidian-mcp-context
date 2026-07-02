from __future__ import annotations

import subprocess


def test_synthetic_demo_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", "scripts/run_synthetic_demo.sh"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr


def test_synthetic_demo_script_prints_help_without_starting_services():
    result = subprocess.run(
        ["bash", "scripts/run_synthetic_demo.sh", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "run_synthetic_demo.sh" in result.stdout
    assert "stop" in result.stdout
    assert "status" in result.stdout
    assert "--fast" in result.stdout
    assert "--initial-limit" in result.stdout


def test_synthetic_demo_script_rejects_unknown_fixture_size_before_docker():
    result = subprocess.run(
        ["bash", "scripts/run_synthetic_demo.sh", "personal-vault", "--no-continuous"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Unknown vault size" in result.stderr


def test_synthetic_demo_script_parses_default_start_options():
    result = subprocess.run(
        ["bash", "scripts/run_synthetic_demo.sh", "--unknown"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Unknown option: --unknown" in result.stderr
