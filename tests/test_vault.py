from pathlib import Path
import json

from obsidian_mcp_context.query import get_note_context, list_tasks, search_blocks
from obsidian_mcp_context.vault import VaultConfig, build_context, scan_vault
from obsidian_mcp_context.warehouse import build_warehouse, list_entities


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


def test_custom_top_level_folders_become_entity_types(tmp_path: Path):
    (tmp_path / "Clients").mkdir()
    (tmp_path / "Assets").mkdir()
    (tmp_path / "Initiatives").mkdir()
    (tmp_path / "Clients" / "Acme Renewal.md").write_text(
        "# Acme Renewal\n\nOwns [[Revenue Dashboard]].\n", encoding="utf-8"
    )
    (tmp_path / "Assets" / "Revenue Dashboard.md").write_text(
        "# Revenue Dashboard\n\nSupports [[Data Trust]].\n", encoding="utf-8"
    )
    (tmp_path / "Initiatives" / "Data Trust.md").write_text(
        "# Data Trust\n\n- [ ] Review [[Acme Renewal]].\n", encoding="utf-8"
    )

    context = build_context(VaultConfig(vault_path=tmp_path))
    warehouse = build_warehouse(context)
    try:
        entities = list_entities(warehouse, limit=100)
    finally:
        warehouse.close()

    assert {(row["entity_type"], row["name"]) for row in entities} >= {
        ("client", "Acme Renewal"),
        ("asset", "Revenue Dashboard"),
        ("initiative", "Data Trust"),
    }


def test_synthetic_vault_represents_connected_renewal_scenario():
    vault_path = Path("examples/synthetic-vault")
    manifest = json.loads((vault_path / "manifest.json").read_text(encoding="utf-8"))

    context = build_context(VaultConfig(vault_path=vault_path))

    source_paths = {file.source_path for file in context.files}
    assert "Companies/Northstar Labs.md" in source_paths
    assert "Meetings/Atlas Renewal Review.md" in source_paths
    assert "Risks/Pilot Handoff Ownership.md" in source_paths
    assert "System/Plain Discovery Notes.txt" not in source_paths

    open_tasks = list_tasks(context, checked=False, limit=100)
    assert len(open_tasks) >= manifest["expected_queries"][0]["minimum_expected_open_tasks"]

    risk_blocks = search_blocks(context, text="Pilot Handoff Ownership", limit=25)
    risk_sources = {block["source_path"] for block in risk_blocks}
    assert {
        "Daily/2026-06-26.md",
        "Risks/Pilot Handoff Ownership.md",
    }.issubset(risk_sources)

    meeting = get_note_context(context, "Meetings/Atlas Renewal Review.md")
    meeting_links = {link["link_target"] for link in meeting["links"]}
    assert "Not A Real Stakeholder" not in meeting_links
    assert "Not A Real Note" not in meeting_links
    assert {"Morgan Lee", "Priya Shah", "Renewal Prep Scope"}.issubset(meeting_links)
