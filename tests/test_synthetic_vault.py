from datetime import datetime
import json
from pathlib import Path
import re

from obsidian_mcp_context.query import get_note_context, list_tasks, search_blocks
from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import build_warehouse, entity_timeline, list_entities


VAULT_PATH = Path("examples/synthetic-vault")
LIFECYCLE_FIELDS = (
    "source_created_at",
    "source_observed_at",
    "created_at",
    "updated_at",
)
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def _manifest() -> dict[str, object]:
    return json.loads((VAULT_PATH / "manifest.json").read_text(encoding="utf-8"))


def test_expanded_synthetic_vault_matches_manifest_scale():
    manifest = _manifest()
    targets = manifest["vault_statistics"]["target_counts"]

    for folder, expected_count in targets.items():
        if folder == "Total_Files":
            continue
        files = list((VAULT_PATH / folder).glob("*.md"))
        assert len(files) >= expected_count, folder

    markdown_files = list(VAULT_PATH.glob("*/*.md"))
    assert len(markdown_files) >= targets["Total_Files"]


def test_expanded_synthetic_vault_has_expected_task_density():
    manifest = _manifest()
    context = build_context(VaultConfig(vault_path=VAULT_PATH))

    open_tasks = list_tasks(context, checked=False, limit=500)
    completed_tasks = list_tasks(context, checked=True, limit=500)

    assert len(open_tasks) >= manifest["vault_statistics"]["minimum_expected_open_tasks"]
    assert (
        len(completed_tasks)
        >= manifest["vault_statistics"]["minimum_expected_completed_tasks"]
    )


def test_synthetic_vault_has_lifecycle_timestamps_on_every_note():
    markdown_files = list(VAULT_PATH.glob("*/*.md"))
    assert markdown_files

    for path in markdown_files:
        frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
        metadata = {}
        for line in frontmatter.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")

        for field in LIFECYCLE_FIELDS:
            assert field in metadata, path
            assert TIMESTAMP_RE.match(metadata[field]), (path, field)

        source_created_at = datetime.fromisoformat(metadata["source_created_at"])
        source_observed_at = datetime.fromisoformat(metadata["source_observed_at"])
        created_at = datetime.fromisoformat(metadata["created_at"])
        updated_at = datetime.fromisoformat(metadata["updated_at"])

        assert source_created_at <= source_observed_at <= created_at <= updated_at


def test_superseded_decision_scenario_is_represented_with_links():
    context = build_context(VaultConfig(vault_path=VAULT_PATH))

    old_decision = get_note_context(context, "Decisions/Renewal Prep Scope.md")
    new_decision = get_note_context(
        context, "Decisions/Revised Security Addendum Scope.md"
    )
    trigger = get_note_context(context, "Meetings/Atlas SecOps Realignment.md")

    old_text = "\n".join(block["text"] for block in old_decision["blocks"])
    new_links = {link["link_target"] for link in new_decision["links"]}
    trigger_links = {link["link_target"] for link in trigger["links"]}

    assert "#superseded" in old_text
    assert "Revised Security Addendum Scope" in {
        link["link_target"] for link in old_decision["links"]
    }
    assert {"Renewal Prep Scope", "Elena Rostova"}.issubset(new_links)
    assert {"Renewal Prep Scope", "Revised Security Addendum Scope"}.issubset(
        trigger_links
    )


def test_marcus_vance_timeline_captures_skeptic_to_sponsor_shift():
    context = build_context(VaultConfig(vault_path=VAULT_PATH))
    warehouse = build_warehouse(context)

    rows = entity_timeline(warehouse, entity="Marcus Vance", limit=100)
    sources = [row["source_path"] for row in rows]
    summaries = "\n".join(row["summary"] for row in rows)

    assert "Meetings/Horizon Kickoff.md" in sources
    assert "Meetings/Horizon Phase 1 Signoff.md" in sources
    assert "Research/Data Lineage Reconciliation Blueprint.md" in sources
    assert sources.index("Meetings/Horizon Kickoff.md") < sources.index(
        "Meetings/Horizon Phase 1 Signoff.md"
    )
    assert "Skeptic" in summaries
    assert "Sponsor" in summaries


def test_acme_reschedule_and_task_mutation_are_represented():
    context = build_context(VaultConfig(vault_path=VAULT_PATH))

    stale_blocks = search_blocks(context, source_path="Daily/2026-05-11.md")
    actual = get_note_context(context, "Meetings/Pipeline Alignment Actual.md")
    completed_on_0519 = list_tasks(
        context,
        checked=True,
        source_path="Daily/2026-05-19.md",
        limit=20,
    )

    stale_text = "\n".join(block["text"] for block in stale_blocks)
    actual_text = "\n".join(block["text"] for block in actual["blocks"])

    assert "2026-05-12" in stale_text
    assert "2026-05-15" in actual_text
    assert {
        "Draft source mapping inventory for [[Acme Corp]] #ops",
        "Send kickoff recap to [[Hannah Brooks]] #follow-up",
        "Ask [[Lina Ortega]] for final DPA confirmation #legal",
    }.issubset({task["task_text"] for task in completed_on_0519})


def test_expanded_entities_are_available_to_warehouse_queries():
    context = build_context(VaultConfig(vault_path=VAULT_PATH))
    warehouse = build_warehouse(context)

    companies = {row["name"] for row in list_entities(warehouse, entity_type="company")}
    people = {row["name"] for row in list_entities(warehouse, entity_type="person")}
    projects = {row["name"] for row in list_entities(warehouse, entity_type="project")}

    assert {"Northstar Labs", "Acme Corp", "Apex FinTech"}.issubset(companies)
    assert {"Elena Rostova", "David Chen", "Marcus Vance"}.issubset(people)
    assert {"Project Atlas", "Project Pipeline", "Project Horizon"}.issubset(projects)
