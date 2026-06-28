from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

import duckdb
import pytest

from obsidian_mcp_context.ingest import ingest_vault


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_SQL_DIR = PROJECT_ROOT / "tests" / "reconciliation"


@pytest.fixture(scope="session")
def synthetic_dbt_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work_dir = tmp_path_factory.mktemp("reconciliation")
    duckdb_path = work_dir / "obsidian.duckdb"

    ingest_vault(PROJECT_ROOT / "examples" / "synthetic-vault", duckdb_path)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dbt.cli.main",
            "run",
            "--profiles-dir",
            "dbt",
            "--project-dir",
            ".",
            "--quiet",
        ],
        cwd=PROJECT_ROOT,
        env=os.environ | {"DUCKDB_PATH": str(duckdb_path)},
        check=True,
    )
    return duckdb_path


def _sql_files() -> list[Path]:
    return sorted(RECONCILIATION_SQL_DIR.glob("*.sql"))


@pytest.mark.parametrize("sql_path", _sql_files(), ids=lambda path: path.name)
def test_reconciliation_sql_returns_no_rows(
    synthetic_dbt_warehouse: Path,
    sql_path: Path,
):
    query = sql_path.read_text(encoding="utf-8")
    connection = duckdb.connect(str(synthetic_dbt_warehouse), read_only=True)
    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()

    assert rows == []
