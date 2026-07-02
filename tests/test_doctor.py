import json
from pathlib import Path

from obsidian_mcp_context.cli import main
from obsidian_mcp_context.doctor import (
    DoctorCode,
    DoctorOptions,
    exit_code,
    format_human,
    run_doctor,
)


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
    assert report["readiness"]["status"] == "warning"
    assert report["readiness"]["blocking"] is False
    assert report["readiness"]["warning_count"] == len(report["warnings"])
    readiness_checks = {
        item["name"]: item for item in report["readiness"]["checks"]
    }
    assert readiness_checks["vault_access"]["status"] == "warning"
    assert readiness_checks["parser"]["status"] == "ready"
    assert readiness_checks["content"]["status"] == "ready"
    assert readiness_checks["graph"]["status"] == "warning"
    assert readiness_checks["warehouse"]["status"] == "ready"
    assert readiness_checks["dbt"]["status"] == "not_checked"
    assert readiness_checks["mcp"]["status"] == "ready"
    assert "Run Postgres ingest and dbt build/test for mart-backed readiness." in report[
        "readiness"
    ]["suggestions"]
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
        "ignored_count": 0,
        "ignored_target_shapes": {},
        "remediation_hints": [
            {
                "code": "create_note",
                "count": 1,
                "message": "Create missing notes or remove unresolved non-path wikilinks.",
                "source": "target_shape:non_path_like",
            }
        ],
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


def test_doctor_does_not_export_unresolved_links_by_default(tmp_path: Path):
    vault = tmp_path / "vault"
    export_path = tmp_path / "unresolved-links.json"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n\n[[Missing Note]]\n", encoding="utf-8")

    report = run_doctor(
        DoctorOptions(vault_path=vault, config_path=tmp_path / "missing-config.toml")
    )

    assert report["graph"]["unresolved_export"] == {
        "requested": False,
        "written": False,
    }
    assert not export_path.exists()


def test_doctor_exports_unresolved_links_when_explicitly_requested(tmp_path: Path):
    vault = tmp_path / "vault"
    export_path = tmp_path / "unresolved-links.json"
    vault.mkdir()
    (vault / "People").mkdir()
    (vault / "People" / "Morgan Lee.md").write_text("# Morgan\n", encoding="utf-8")
    (vault / "Links.md").write_text(
        "\n".join(
            [
                "[[Missing Note]]",
                "[[Archive/Morgan Lee]]",
                "[[Archive/Morgan Lee]]",
            ]
        ),
        encoding="utf-8",
    )

    report = run_doctor(
        DoctorOptions(
            vault_path=vault,
            config_path=tmp_path / "missing-config.toml",
            export_unresolved_path=export_path,
        )
    )

    assert report["graph"]["top_unresolved_targets"] == []
    assert report["graph"]["unresolved_export"] == {
        "requested": True,
        "written": True,
        "target_count": 2,
        "path": str(export_path),
    }
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["privacy"] == {
        "contains_private_targets": True,
        "contains_source_paths": False,
        "intended_for_local_use_only": True,
    }
    assert payload["unresolved_target_count"] == 2
    assert payload["unresolved_targets"] == [
        {
            "target": "Archive/Morgan Lee",
            "target_shape": "path_like",
            "reason": "basename_exists_elsewhere",
            "count": 2,
            "ignored": False,
            "source_count": 1,
        },
        {
            "target": "Missing Note",
            "target_shape": "plain_text",
            "reason": "",
            "count": 1,
            "ignored": False,
            "source_count": 1,
        },
    ]


def test_doctor_export_includes_source_paths_only_with_samples(tmp_path: Path):
    vault = tmp_path / "vault"
    export_path = tmp_path / "unresolved-links.json"
    vault.mkdir()
    (vault / "One.md").write_text("[[Missing Note]]\n", encoding="utf-8")
    (vault / "Two.md").write_text("[[Missing Note]]\n", encoding="utf-8")

    report = run_doctor(
        DoctorOptions(
            vault_path=vault,
            config_path=tmp_path / "missing-config.toml",
            include_samples=True,
            export_unresolved_path=export_path,
        )
    )

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert report["graph"]["unresolved_export"]["target_count"] == 1
    assert payload["privacy"]["contains_source_paths"] is True
    assert payload["unresolved_targets"] == [
        {
            "target": "Missing Note",
            "target_shape": "plain_text",
            "reason": "",
            "count": 2,
            "ignored": False,
            "source_count": 2,
            "source_paths": ["One.md", "Two.md"],
        }
    ]


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
    assert unresolved["details"]["ignored_count"] == 0
    assert unresolved["details"]["ignored_target_shapes"] == {}
    assert unresolved["details"]["remediation_hints"] == [
        {
            "code": "create_note",
            "count": 2,
            "message": "Create missing notes or remove links with no matching candidate.",
            "source": "path_like_reason:no_candidate_found",
        },
        {
            "code": "create_note",
            "count": 5,
            "message": "Create missing notes or remove unresolved non-path wikilinks.",
            "source": "target_shape:non_path_like",
        },
    ]
    assert "top_targets" not in unresolved["details"]


def test_doctor_ignores_configured_unresolved_target_globs(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Links.md").write_text(
        "\n".join(
            [
                "[[Archive/Intentional Missing]]",
                "[[Template:Client]]",
                "[[Needs Review]]",
            ]
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[doctor.unresolved_wikilinks]
mode = "warn"
ignore_target_globs = ["Archive/*", "Template:*"]
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["status"] == "warning"
    assert report["config"]["doctor"]["unresolved_wikilinks"] == "warn"
    assert report["config"]["doctor"]["unresolved_wikilink_ignore_target_globs"] == [
        "Archive/*",
        "Template:*",
    ]
    assert report["graph"]["unresolved_wikilinks"] == 3
    assert report["graph"]["ignored_unresolved_wikilinks"] == 2
    assert report["graph"]["warning_unresolved_wikilinks"] == 1
    assert report["graph"]["ignored_unresolved_target_shapes"] == {
        "path_like": 1,
        "plain_text": 1,
    }
    assert report["graph"]["warning_unresolved_target_shapes"] == {"plain_text": 1}
    assert report["graph"]["top_unresolved_targets"] == []
    unresolved = next(
        item
        for item in report["diagnostics"]
        if item["code"] == DoctorCode.UNRESOLVED_WIKILINK.value
    )
    assert unresolved["details"] == {
        "count": 1,
        "ignored_count": 2,
        "ignored_target_shapes": {"path_like": 1, "plain_text": 1},
        "path_like_reasons": {},
        "remediation_hints": [
            {
                "code": "create_note",
                "count": 1,
                "message": "Create missing notes or remove unresolved non-path wikilinks.",
                "source": "target_shape:non_path_like",
            },
            {
                "code": "review_ignored_patterns",
                "count": 2,
                "message": (
                    "Review unresolved ignore patterns periodically to confirm they "
                    "still describe intentional dangling links."
                ),
                "source": "ignored_unresolved_wikilinks",
            },
        ],
        "samples_redacted": True,
        "target_shapes": {"plain_text": 1},
    }


def test_doctor_ignores_all_matching_unresolved_targets_without_warning(
    tmp_path: Path,
):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Links.md").write_text(
        "[[Archive/Intentional Missing]]\n[[Template:Client]]\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[doctor]
lifecycle_metadata = "ignore"

[doctor.unresolved_wikilinks]
mode = "warn"
ignore_target_globs = ["Archive/*", "Template:*"]
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))

    assert report["status"] == "ok"
    assert report["graph"]["unresolved_wikilinks"] == 2
    assert report["graph"]["ignored_unresolved_wikilinks"] == 2
    assert report["graph"]["warning_unresolved_wikilinks"] == 0
    assert report["graph"]["unresolved_remediation_hints"] == [
        {
            "code": "review_ignored_patterns",
            "count": 2,
            "message": (
                "Review unresolved ignore patterns periodically to confirm they "
                "still describe intentional dangling links."
            ),
            "source": "ignored_unresolved_wikilinks",
        }
    ]
    assert DoctorCode.UNRESOLVED_WIKILINK.value not in {
        item["code"] for item in report["diagnostics"]
    }


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
    assert report["graph"]["unresolved_remediation_hints"] == [
        {
            "code": "normalize_link_path",
            "count": 1,
            "message": "Update links whose basename exists elsewhere but not at the linked path.",
            "source": "path_like_reason:basename_exists_elsewhere",
        },
        {
            "code": "adjust_scan_excludes",
            "count": 1,
            "message": "Review scan excludes for linked notes that exist under excluded paths.",
            "source": "path_like_reason:excluded_path",
        },
        {
            "code": "adjust_scan_includes",
            "count": 1,
            "message": "Review scan include globs for Markdown candidates outside the scanned set.",
            "source": "path_like_reason:missing_extension_candidate",
        },
        {
            "code": "create_note",
            "count": 1,
            "message": "Create missing notes or remove links with no matching candidate.",
            "source": "path_like_reason:no_candidate_found",
        },
        {
            "code": "include_extension",
            "count": 1,
            "message": "Review source extensions for linked files that exist with unsupported extensions.",
            "source": "path_like_reason:unsupported_extension",
        },
    ]
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


def test_doctor_human_output_includes_aggregate_remediation_hints(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Links.md").write_text("[[Missing/Path]]\n", encoding="utf-8")

    report = run_doctor(
        DoctorOptions(vault_path=vault, config_path=tmp_path / "missing-config.toml")
    )
    output = format_human(report)

    assert "Unresolved wikilink remediation hints:" in output
    assert "Readiness: WARNING" in output
    assert "Readiness suggestions:" in output
    assert "create_note: 1" in output
    assert "Missing/Path" not in output


def test_doctor_readiness_blocks_unusable_scan(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note.txt").write_text("Not markdown\n", encoding="utf-8")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[scan]
include_globs = ["**/*.md"]
source_extensions = [".md"]
""".strip(),
        encoding="utf-8",
    )

    report = run_doctor(DoctorOptions(vault_path=vault, config_path=config_path))
    readiness_checks = {
        item["name"]: item for item in report["readiness"]["checks"]
    }

    assert report["status"] == "error"
    assert report["readiness"]["status"] == "blocked"
    assert report["readiness"]["blocking"] is True
    assert readiness_checks["vault_access"]["status"] == "blocked"
    assert readiness_checks["parser"]["status"] == "blocked"
    assert readiness_checks["mcp"]["status"] == "blocked"
    assert "Review scan include/exclude globs so Markdown files are scanned." in report[
        "readiness"
    ]["suggestions"]


def test_doctor_readiness_doc_describes_json_contract_and_privacy():
    docs = Path("docs/doctor-readiness.md").read_text(encoding="utf-8")

    for value in [
        "readiness.status",
        "readiness.checks",
        "profile",
        "vault_access",
        "parser",
        "content",
        "graph",
        "warehouse",
        "dbt",
        "mcp",
        "not_checked",
        "var/generated-doctor-readiness.json",
    ]:
        assert value in docs
    assert "$VAULT_PATH" in docs


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


def test_doctor_cli_exports_unresolved_links(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    export_path = tmp_path / "unresolved-links.json"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n\n[[Missing Note]]\n", encoding="utf-8")

    result = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(tmp_path / "missing-config.toml"),
            "doctor",
            "--json",
            "--export-unresolved",
            str(export_path),
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert '"top_unresolved_targets": []' in captured.out
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["unresolved_targets"][0]["target"] == "Missing Note"
