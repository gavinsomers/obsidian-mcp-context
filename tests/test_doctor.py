from pathlib import Path

import duckdb

from obsidian_mcp_context.cli import main
from obsidian_mcp_context.doctor import DoctorOptions, exit_code, run_doctor


def test_doctor_reports_parser_graph_and_warehouse_readiness(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "People").mkdir()
    (vault / "Daily").mkdir()
    (vault / "People" / "Morgan Lee.md").write_text(
        """---
source_created_at: 2026-06-01T09:00:00
source_observed_at: 2026-06-01T09:05:00
created_at: 2026-06-01T09:10:00
updated_at: 2026-06-01T09:20:00
---
# Morgan Lee
""",
        encoding="utf-8",
    )
    (vault / "Daily" / "2026-06-28.md").write_text(
        """---
source_created_at: 2026-06-28T09:00:00
source_observed_at: 2026-06-28T09:05:00
created_at: 2026-06-28T09:10:00
updated_at: 2026-06-28T09:20:00
---
# Daily

- [ ] Follow up with [[Morgan Lee]] and [[Missing Person]] #ops
""",
        encoding="utf-8",
    )
    (vault / "image.png").write_bytes(b"ignored")

    report = run_doctor(DoctorOptions(vault_path=vault))

    assert report["status"] == "warning"
    assert report["vault"]["markdown_file_count"] == 2
    assert report["parser"]["tasks"] == 1
    assert report["parser"]["links"] == 2
    assert report["graph"]["resolved_wikilinks"] == 1
    assert report["graph"]["unresolved_wikilinks"] == 1
    assert report["warehouse"]["in_memory"]["ok"] is True
    assert exit_code(report) == 0
    assert exit_code(report, strict=True) == 1


def test_doctor_validates_optional_duckdb_warehouse(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    duckdb_path = tmp_path / "partial.duckdb"
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute("create table dim_notes (note_id text)")
    finally:
        connection.close()

    report = run_doctor(DoctorOptions(vault_path=vault, duckdb_path=duckdb_path))

    assert report["status"] == "error"
    assert report["warehouse"]["duckdb"]["exists"] is True
    assert report["warehouse"]["duckdb"]["required_marts_available"] is False
    assert exit_code(report) == 2


def test_doctor_cli_outputs_json(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")

    result = main(["--vault", str(vault), "doctor", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"status": "warning"' in captured.out
