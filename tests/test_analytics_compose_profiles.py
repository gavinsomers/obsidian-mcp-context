from __future__ import annotations

import subprocess
from pathlib import Path


COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env.analytics.example",
    "-f",
    "docker-compose.analytics.yml",
]


def _compose_services(*extra_args: str) -> set[str]:
    result = subprocess.run(
        [*COMPOSE, *extra_args, "config", "--services"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    return set(result.stdout.splitlines())


def test_default_analytics_compose_services_are_quiet_pipeline_surface():
    services = _compose_services()

    assert {"postgres", "ingest", "dbt", "dbt-test", "mcp"}.issubset(services)
    assert "vault-obsidian" not in services
    assert "replay-dashboard" not in services
    assert "replay-qa" not in services
    assert "dbt-docs" not in services
    assert "postgres-browser" not in services


def test_inspection_profile_exposes_dbt_docs_and_table_browser():
    services = _compose_services("--profile", "inspection")

    assert "dbt-docs" in services
    assert "dbt-docs-generate" in services
    assert "postgres-browser" in services
    assert "vault-obsidian" not in services
    assert "replay-dashboard" not in services


def test_legacy_replay_and_obsidian_profiles_are_explicit():
    replay_services = _compose_services("--profile", "legacy-replay")
    obsidian_services = _compose_services("--profile", "obsidian")

    assert "replay-dashboard" in replay_services
    assert "replay-qa" in replay_services
    assert "vault-obsidian" not in replay_services
    assert "vault-obsidian" in obsidian_services
    assert "replay-dashboard" not in obsidian_services


def test_workflow_profile_exposes_dataset_workflow_orchestrator():
    services = _compose_services("--profile", "workflow")

    assert "dataset-workflow" in services
    assert "vault-obsidian" not in services
    assert "replay-dashboard" not in services
    assert "replay-qa" not in services


def test_workflow_resets_split_warehouse_schemas_before_dbt_run():
    compose = Path("docker-compose.analytics.yml").read_text(encoding="utf-8")

    assert "RESET_WAREHOUSE_SCHEMAS" in compose
    assert "dbt run-operation reset_warehouse_schemas" in compose
    assert "POSTGRES_WAREHOUSE_SCHEMAS" in compose
