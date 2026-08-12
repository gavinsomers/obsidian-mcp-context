from pathlib import Path
import json

from obsidian_mcp_context.query import get_note_context, list_tasks, search_blocks
from obsidian_mcp_context.vault import VaultConfig, build_context, scan_vault
from obsidian_mcp_context.warehouse import build_warehouse, list_entities


def test_scan_vault_respects_excludes(tmp_path: Path):
    (tmp_path / "daily").mkdir()
    (tmp_path / "daily" / "today.md").write_text("- [ ] Task\n", encoding="utf-8")
    (tmp_path / "system" / "marts").mkdir(parents=True)
    (tmp_path / "system" / "marts" / "open_loops.md").write_text(
        "generated\n", encoding="utf-8"
    )

    files = scan_vault(VaultConfig(vault_path=tmp_path))

    assert [file.source_path for file in files] == ["daily/today.md"]


def test_build_context_searches_generic_markdown(tmp_path: Path):
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "atlas.md").write_text(
        """# Project Atlas

Renewal workflow notes link to [[Morgan Lee]].

## Next Steps

- [ ] Draft renewal checklist #ops
""",
        encoding="utf-8",
    )

    context = build_context(VaultConfig(vault_path=tmp_path))

    assert search_blocks(context, text="renewal")[0]["source_path"] == "projects/atlas.md"
    assert list_tasks(context, checked=False)[0]["task_text"] == "Draft renewal checklist #ops"
    note = get_note_context(context, "projects/atlas.md")
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
    (tmp_path / "clients").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "initiatives").mkdir()
    (tmp_path / "clients" / "acme_renewal.md").write_text(
        "# Acme Renewal\n\nOwns [[Revenue Dashboard]].\n", encoding="utf-8"
    )
    (tmp_path / "assets" / "revenue_dashboard.md").write_text(
        "# Revenue Dashboard\n\nSupports [[Data Trust]].\n", encoding="utf-8"
    )
    (tmp_path / "initiatives" / "data_trust.md").write_text(
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
    assert "companies/northstar_labs.md" in source_paths
    assert "meetings/atlas_renewal_review.md" in source_paths
    assert "risks/pilot_handoff_ownership.md" in source_paths
    assert "system/plain_discovery_notes.txt" not in source_paths

    open_tasks = list_tasks(context, checked=False, limit=100)
    assert len(open_tasks) >= manifest["expected_queries"][0]["minimum_expected_open_tasks"]

    risk_blocks = search_blocks(context, text="Pilot Handoff Ownership", limit=25)
    risk_sources = {block["source_path"] for block in risk_blocks}
    assert {
        "daily/2026-06-26.md",
        "risks/pilot_handoff_ownership.md",
    }.issubset(risk_sources)

    meeting = get_note_context(context, "meetings/atlas_renewal_review.md")
    meeting_links = {link["link_target"] for link in meeting["links"]}
    assert "Not A Real Stakeholder" not in meeting_links
    assert "Not A Real Note" not in meeting_links
    assert {"Morgan Lee", "Priya Shah", "Renewal Prep Scope"}.issubset(meeting_links)
