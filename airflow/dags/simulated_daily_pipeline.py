from __future__ import annotations

from datetime import datetime, timedelta
import os

from airflow import DAG
from airflow.operators.bash import BashOperator


SEED_VAULT = os.environ.get("SIM_SEED_VAULT", "/seed-vault")
LIVE_VAULT = os.environ.get("SIM_LIVE_VAULT", "/live-vault")
STATE_PATH = os.environ.get("SIM_STATE_PATH", "/warehouse/simulation-state.json")
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "/warehouse/obsidian.duckdb")
PROFILE = os.environ.get("SIM_PROFILE", "medium")
SEED = os.environ.get("SIM_SEED", "42")
VIRTUAL_DAYS_PER_RUN = os.environ.get("SIM_VIRTUAL_DAYS_PER_RUN", "12")


with DAG(
    dag_id="simulated_daily_obsidian_pipeline",
    description="Advance a virtual Obsidian vault and run ingest/dbt once per minute.",
    start_date=datetime(2026, 1, 1),
    schedule=timedelta(minutes=1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0},
    tags=["obsidian", "simulation"],
) as dag:
    ensure_seed_vault = BashOperator(
        task_id="ensure_seed_vault",
        bash_command=(
            f"test -f {SEED_VAULT}/manifest.json || "
            "obsidian-mcp-context-generate-vault "
            f"--profile {PROFILE} --seed {SEED} --output {SEED_VAULT} --force"
        ),
    )

    advance_virtual_days = BashOperator(
        task_id="advance_virtual_days",
        bash_command=(
            "obsidian-mcp-context-simulate-vault advance "
            f"--seed-vault {SEED_VAULT} "
            f"--live-vault {LIVE_VAULT} "
            f"--state {STATE_PATH} "
            f"--days {VIRTUAL_DAYS_PER_RUN}"
        ),
    )

    ingest_live_vault = BashOperator(
        task_id="ingest_live_vault",
        bash_command=(
            "obsidian-mcp-context-ingest "
            f"--vault {LIVE_VAULT} "
            f"--duckdb {DUCKDB_PATH}"
        ),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"DUCKDB_PATH={DUCKDB_PATH} dbt run --profiles-dir dbt",
        cwd="/app",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"DUCKDB_PATH={DUCKDB_PATH} dbt test --profiles-dir dbt",
        cwd="/app",
    )

    ensure_seed_vault >> advance_virtual_days >> ingest_live_vault >> dbt_run >> dbt_test
