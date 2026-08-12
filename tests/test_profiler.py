from __future__ import annotations

import json
from pathlib import Path

from obsidian_mcp_context.cli import main as cli_main
from obsidian_mcp_context.profiler import (
    ProfilerOptions,
    main as profiler_main,
    profile_vault,
    write_profile_report,
)


def _profile_fixture(vault: Path) -> None:
    (vault / "Accounts").mkdir(parents=True)
    (vault / "Logs").mkdir()
    (vault / "Raw").mkdir()
    (vault / "Accounts" / "Acme.md").write_text(
        """---
source_created_at: 2026-06-01T09:00:00
source_observed_at: 2026-06-01T09:05:00
created_at: 2026-06-01T09:10:00
updated_at: 2026-06-01T09:15:00
status: active
---
# Acme

Links to [[Call One]] and [[logs/call_one|call]].

- [ ] Follow up #client
""",
        encoding="utf-8",
    )
    (vault / "Logs" / "Call One.md").write_text(
        "# Call One\n\nDiscussed [[2026-06-01]] #meeting\n",
        encoding="utf-8",
    )
    (vault / "Raw" / "Ignored.md").write_text("# Ignored\n", encoding="utf-8")
    (vault / "Raw" / "Attachment.pdf").write_text("not markdown\n", encoding="utf-8")
    (vault / "empty.md").write_text("", encoding="utf-8")


def test_profile_vault_writes_aggregate_report_without_private_paths(tmp_path: Path):
    vault = tmp_path / "vault"
    profile_path = tmp_path / "profile.toml"
    output_path = tmp_path / "var" / "vault-profile-report.json"
    _profile_fixture(vault)
    profile_path.write_text(
        """
[scan]
include_globs = ["**/*.md", "Raw/*.pdf"]
extra_exclude_globs = ["Raw/Ignored.md"]

[entities]
non_entity_note_types = ["log", "note"]

[entities.folders]
Accounts = "account"
Logs = "log"
""".strip(),
        encoding="utf-8",
    )

    report = profile_vault(
        ProfilerOptions(
            vault_path=vault,
            config_path=tmp_path / "missing.toml",
            profile_path=profile_path,
            output_path=output_path,
        )
    )
    write_profile_report(report, output_path)
    payload = output_path.read_text(encoding="utf-8")

    assert report["privacy"] == {
        "read_only": True,
        "source_paths_redacted": True,
        "note_content_included": False,
    }
    assert report["files"]["scanned_source_file_count"] == 3
    assert report["files"]["unsupported_included_file_count"] == 1
    assert report["files"]["note_types"] == {
        "account": 1,
        "log": 1,
        "note": 1,
    }
    assert report["frontmatter"]["files_with_frontmatter"] == 1
    assert report["frontmatter"]["lifecycle_field_coverage"]["created_at"] == {
        "count": 1,
        "coverage_ratio": 0.3333,
    }
    assert report["graph"]["wikilink_shapes"] == {
        "date_like": 1,
        "path_like": 1,
        "title_like": 1,
    }
    assert report["graph"]["unique_tags"] == 2
    assert report["content"]["empty_note_count"] == 1
    assert report["samples"]["redacted"] is True
    assert report["samples"]["ignored_paths"] == []
    assert str(vault) not in payload
    assert "Accounts/Acme.md" not in payload
    assert "Follow up" not in payload


def test_profile_vault_can_include_local_path_samples_when_explicit(
    tmp_path: Path,
):
    vault = tmp_path / "vault"
    _profile_fixture(vault)

    report = profile_vault(
        ProfilerOptions(
            vault_path=vault,
            config_path=tmp_path / "missing.toml",
            include_samples=True,
        )
    )

    assert report["privacy"]["source_paths_redacted"] is False
    assert "empty.md" in report["samples"]["empty_notes"]


def test_profiler_entrypoint_writes_default_json_shape(tmp_path: Path):
    vault = tmp_path / "vault"
    output_path = tmp_path / "report.json"
    _profile_fixture(vault)

    result = profiler_main(
        [
            "--vault",
            str(vault),
            "--config",
            str(tmp_path / "missing.toml"),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == 0
    assert payload["type"] == "vault_profile_report"
    assert payload["privacy"]["note_content_included"] is False


def test_cli_profile_vault_command_writes_report(tmp_path: Path, capsys):
    vault = tmp_path / "vault"
    output_path = tmp_path / "report.json"
    _profile_fixture(vault)

    result = cli_main(
        [
            "--vault",
            str(vault),
            "--config",
            str(tmp_path / "missing.toml"),
            "profile-vault",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert output_path.exists()
    assert '"type": "vault_profile_report"' in captured.out
    assert "Vault profile report written" in captured.out
