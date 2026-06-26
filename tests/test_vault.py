from pathlib import Path

from obsidian_mcp_context.query import get_note_context, list_tasks, search_blocks
from obsidian_mcp_context.vault import VaultConfig, build_context, scan_vault


def test_scan_vault_respects_excludes(tmp_path: Path):
    (tmp_path / "Daily").mkdir()
    (tmp_path / "Daily" / "today.md").write_text("- [ ] Task\n", encoding="utf-8")
    (tmp_path / "System" / "Marts").mkdir(parents=True)
    (tmp_path / "System" / "Marts" / "Open Loops.md").write_text(
        "generated\n", encoding="utf-8"
    )

    files = scan_vault(VaultConfig(vault_path=tmp_path))

    assert [file.source_path for file in files] == ["Daily/today.md"]


def test_build_context_searches_generic_markdown(tmp_path: Path):
    (tmp_path / "Projects").mkdir()
    (tmp_path / "Projects" / "Atlas.md").write_text(
        """# Project Atlas

Renewal workflow notes link to [[Morgan Lee]].

## Next Steps

- [ ] Draft renewal checklist #ops
""",
        encoding="utf-8",
    )

    context = build_context(VaultConfig(vault_path=tmp_path))

    assert search_blocks(context, text="renewal")[0]["source_path"] == "Projects/Atlas.md"
    assert list_tasks(context, checked=False)[0]["task_text"] == "Draft renewal checklist #ops"
    note = get_note_context(context, "Projects/Atlas.md")
    assert note["links"][0]["link_target"] == "Morgan Lee"
    assert note["tags"][0]["tag"] == "ops"


def test_plain_text_is_opt_in_generic_only(tmp_path: Path):
    (tmp_path / "Notes").mkdir()
    (tmp_path / "Notes" / "plain.txt").write_text(
        "Plain text line with #tag and [[Link]].\n", encoding="utf-8"
    )

    default_context = build_context(VaultConfig(vault_path=tmp_path))
    assert default_context.files == []

    text_context = build_context(
        VaultConfig(
            vault_path=tmp_path,
            include_globs=("**/*.txt",),
            source_extensions=(".txt",),
        )
    )
    assert len(text_context.lines) == 1
    assert text_context.tasks == []
    assert text_context.links == []
    assert text_context.tags == []
