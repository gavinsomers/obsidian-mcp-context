from __future__ import annotations

import json
from pathlib import Path

from obsidian_mcp_context.replay_loader import (
    ReplayOptions,
    build_replay_manifest,
    main,
    run_replay,
)


def _write_note(root: Path, relative_path: str, frontmatter: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n# {path.stem}\n", encoding="utf-8")


def test_manifest_uses_created_at_order_and_preserves_relative_paths(tmp_path):
    source = tmp_path / "source"
    _write_note(
        source,
        "Projects/Later.md",
        "created_at: 2023-05-02T09:00:00\n",
    )
    _write_note(
        source,
        "Daily/2023-04-20.md",
        "date: 2023-04-20\n",
    )
    _write_note(
        source,
        "Projects/Earlier.md",
        "created_at: 2023-04-19T10:00:00\n",
    )

    entries = build_replay_manifest(source)

    assert [entry.relative_path for entry in entries] == [
        "Projects/Earlier.md",
        "Daily/2023-04-20.md",
        "Projects/Later.md",
    ]
    assert [entry.timestamp_source for entry in entries] == [
        "created_at",
        "date",
        "created_at",
    ]


def test_dry_run_does_not_create_target_or_state(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_note(source, "Projects/One.md", "created_at: 2023-04-19T10:00:00\n")

    report = run_replay(ReplayOptions(source=source, target=target, dry_run=True))

    assert report["status"] == "dry_run"
    assert report["total_count"] == 1
    assert not target.exists()


def test_replay_copies_files_records_state_and_resume_skips_loaded(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_note(source, "Projects/One.md", "created_at: 2023-04-19T10:00:00\n")
    _write_note(source, "Projects/Two.md", "created_at: 2023-04-20T10:00:00\n")

    first = run_replay(ReplayOptions(source=source, target=target, limit=1))

    assert first["copied_count"] == 1
    assert (target / "Projects/One.md").exists()
    assert not (target / "Projects/Two.md").exists()

    second = run_replay(ReplayOptions(source=source, target=target))
    state = json.loads(
        (target / ".obsidian-mcp-replay-state.json").read_text(encoding="utf-8")
    )

    assert second["copied_count"] == 1
    assert state["loaded_count"] == 2
    assert state["remaining_count"] == 0
    assert state["loaded_files"] == ["Projects/One.md", "Projects/Two.md"]
    assert (target / "Projects/Two.md").exists()


def test_reset_removes_existing_target_contents(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_note(source, "Projects/One.md", "created_at: 2023-04-19T10:00:00\n")
    stale = target / "Stale.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("stale", encoding="utf-8")

    run_replay(ReplayOptions(source=source, target=target, reset=True))

    assert not stale.exists()
    assert (target / "Projects/One.md").exists()


def test_cli_prints_json_report(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_note(source, "Projects/One.md", "created_at: 2023-04-19T10:00:00\n")

    exit_code = main(
        [
            "--source",
            str(source),
            "--target",
            str(target),
            "--dry-run",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "dry_run"
    assert output["total_count"] == 1
