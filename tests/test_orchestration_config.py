from __future__ import annotations

from pathlib import Path


def test_airflow_dag_publishes_tested_duckdb_read_snapshot():
    dag_source = Path("airflow/dags/simulated_daily_pipeline.py").read_text()

    assert 'READ_DUCKDB_PATH", "/warehouse/obsidian-read.duckdb"' in dag_source
    assert 'task_id="publish_read_snapshot"' in dag_source
    assert "dbt_test\n        >> publish_read_snapshot" in dag_source


def test_docker_readers_use_published_duckdb_snapshot():
    compose_source = Path("docker-compose.yml").read_text()

    assert "DUCKDB_PATH: /warehouse/obsidian.duckdb" in compose_source
    assert "READ_DUCKDB_PATH: /warehouse/obsidian-read.duckdb" in compose_source
    assert "DUCKDB_PATH: /warehouse/obsidian-read.duckdb" in compose_source
    assert (
        "mv /warehouse/obsidian-read.duckdb.tmp /warehouse/obsidian-read.duckdb"
        in compose_source
    )
