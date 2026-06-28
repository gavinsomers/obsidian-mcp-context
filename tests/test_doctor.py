from pathlib import Path

import duckdb

from obsidian_mcp_context.cli import main
from obsidian_mcp_context.doctor import DoctorCode, DoctorOptions, exit_code, run_doctor


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

    report = run_doctor(
        DoctorOptions(vault_path=vault, config_path=tmp_path / "missing-config.toml")
    )

    assert report["status"] == "warning"
    assert report["vault"]["markdown_file_count"] == 2
    assert report["parser"]["tasks"] == 1
    assert report["parser"]["links"] == 2
    assert report["graph"]["resolved_wikilinks"] == 1
    assert report["graph"]["unresolved_wikilinks"] == 1
    assert report["warehouse"]["in_memory"]["ok"] is True
    assert {item["code"] for item in report["diagnostics"]} >= {
        DoctorCode.UNSUPPORTED_FILE.value,
        DoctorCode.UNRESOLVED_WIKILINK.value,
    }
    assert DoctorCode.IGNORED_FILE.value not in {
        item["code"] for item in report["diagnostics"]
    }
    assert report["privacy"] == {
        "samples_included": False,
        "samples_redacted": True,
    }
    assert report["content"]["unsupported_file_count"] == 1
    assert report["content"]["unsupported_files"] == []
    assert report["graph"]["top_unresolved_targets"] == []
    unresolved = next(
        item
        for item in report["diagnostics"]
        if item["code"] == DoctorCode.UNRESOLVED_WIKILINK.value
    )
    assert unresolved["details"] == {
        "count": 1,
        "samples_redacted": True,
        "path_like_reasons": {},
        "target_shapes": {"plain_text": 1},
    }
    assert exit_code(report) == 0
    assert exit_code(report, strict=True) == 1


def test_doctor_can_include_samples_when_explicitly_requested(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n\n[[Missing Note]]\n", encoding="utf-8")
    (vault / "image.png").write_bytes(b"ignored")

    report = run_doctor(
        DoctorOptions(
            vault_path=vault,
            config_path=tmp_path / "missing-config.toml",
            include_samples=True,
        )
    )

    assert report["privacy"] == {
        "samples_included": True,
        "samples_redacted": False,
    }
    assert report["content"]["unsupported_files"] == ["image.png"]
    assert report["graph"]["top_unresolved_targets"] == [
        {"target": "Missing Note", "count": 1}
    ]
    unresolved = next(
        item
        for item in report["diagnostics"]
        if item["code"] == DoctorCode.UNRESOLVED_WIKILINK.value
    )
    assert unresolved["details"]["top_targets"] == [
        {"target": "Missing Note", "count": 1}
    ]
    assert unresolved["details"]["target_shapes"] == {"plain_text": 1}


def test_doctor_resolves_obsidian_link_target_variants(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "People").mkdir()
    (vault / "People" / "Morgan Lee.md").write_text(
        """---
aliases:
  - ML
alias: Morgan
---
# Morgan Lee

## Profile
""",
        encoding="utf-8",
    )
    (vault / "Links.md").write_text(
        "\n".join(
            [
                "[[Morgan Lee]]",
                "[[People/Morgan Lee]]",
                "[[People/Morgan Lee.md]]",
                "[[Morgan Lee#Profile]]",
                "[[Morgan Lee^block-id]]",
                "[[ML]]",
                "[[Morgan]]",
                "[[Missing]]",
            ]
        ),
        encoding="utf-8",
    )

    report = run_doctor(
        DoctorOptions(vault_path=vault, config_path=tmp_path / "missing-config.toml")
    )

    assert report["graph"]["wikilinks"] == 8
    assert report["graph"]["resolved_wikilinks"] == 7
    assert report["graph"]["unresolved_wikilinks"] == 1
    assert report["graph"]["unresolved_target_shapes"] == {"plain_text": 1}


def test_doctor_reports_unresolved_link_target_shapes_without_samples(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Links.md").write_text(
        "\n".join(
            [
                "[[Missing Plain]]",
                "[[Missing/Path]]",
                "[[Missing.md]]",
                "[[Missing#Heading]]",
                "[[Missing^block-id]]",
                "[[2026-06-28]]",
                "[[https://example.test/page]]",
            ]
        ),
        encoding="utf-8",
    )

    report = run_doctor(
        DoctorOptions(vault_path=vault, config_path=tmp_path / "missing-config.toml")
    )

    assert report["graph"]["unresolved_target_shapes"] == {
        "block_reference": 1,
        "date_like": 1,
        "heading_reference": 1,
        "path_like": 2,
        "plain_text": 1,
        "url_like": 1,
    }
    assert report["graph"]["top_unresolved_targets"] == []
    unresolved = next(
        item
        for item in report["diagnostics"]
        if item["code"] == DoctorCode.UNRESOLVED_WIKILINK.value
    )
    assert unresolved["details"]["target_shapes"] == report["graph"][
        "unresolved_target_shapes"
    ]
    assert unresolved["details"]["path_like_reasons"] == {
        "no_candidate_found": 2,
    }
    assert "top_targets" not in unresolved["details"]


def test_doctor_classifies_unresolved_path_like_reasons_without_samples(
    tmp_path: Path,
):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "People").mkdir()
    (vault / "Archive").mkdir()
    (vault / "Assets").mkdir()
    (vault / "Drafts").mkdir()
    (vault / "People" / "Morgan Lee.md").write_text("# Morgan\n", encoding="utf-8")
    (vault / "Archive" / "Hidden.md").write_text("# Hidden\n", encoding="utf-8")
    (vault / "Assets" / "Manual.pdf").write_bytes(b"PDF")
    (vault / "Drafts" / "Idea.md").write_text("# Idea\n", encoding="utf-8")
    (vault / "Links.md").write_text(
        "\n".join(
            [
                "[[Archive/Hidden]]",
                "[[Assets/Manual.pdf]]",
                "[[Drafts/Idea]]",
                "[[Archive/Morgan Lee]]",
                "[[Missing/Path]]",
            ]
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[scan]
include_globs = ["Links.md", "People/*.md", "Archive/*.md", "Assets/*.md"]
extra_exclude_globs = ["Archive/Hidden.md"]

[doctor]
lifecycle_metadata = "ignore"
unsupported_files = "ignore"
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["graph"]["unresolved_target_shapes"] == {"path_like": 5}
    assert report["graph"]["unresolved_path_like_reasons"] == {
        "basename_exists_elsewhere": 1,
        "excluded_path": 1,
        "missing_extension_candidate": 1,
        "no_candidate_found": 1,
        "unsupported_extension": 1,
    }
    assert report["graph"]["top_unresolved_targets"] == []
    unresolved = next(
        item
        for item in report["diagnostics"]
        if item["code"] == DoctorCode.UNRESOLVED_WIKILINK.value
    )
    assert unresolved["details"]["path_like_reasons"] == report["graph"][
        "unresolved_path_like_reasons"
    ]
    assert unresolved["details"]["samples_redacted"] is True
    assert "top_targets" not in unresolved["details"]


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

    report = run_doctor(
        DoctorOptions(
            vault_path=vault,
            duckdb_path=duckdb_path,
            config_path=tmp_path / "missing-config.toml",
        )
    )

    assert report["status"] == "error"
    assert report["warehouse"]["duckdb"]["exists"] is True
    assert report["warehouse"]["duckdb"]["required_marts_available"] is False
    assert any(
        item["code"] == DoctorCode.WAREHOUSE_INCOMPLETE.value
        for item in report["diagnostics"]
    )
    assert exit_code(report) == 2


def test_doctor_cli_outputs_json(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")

    result = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(tmp_path / "missing-config.toml"),
            "doctor",
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert '"status": "warning"' in captured.out
    assert '"diagnostics": [' in captured.out
