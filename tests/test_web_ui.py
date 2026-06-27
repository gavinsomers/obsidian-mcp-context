from pathlib import Path

from obsidian_mcp_context.web_ui import answer_question


def test_web_ui_answers_timeline_question_from_synthetic_vault():
    answer = answer_question(
        Path("examples/synthetic-vault"),
        "timeline interactions with Marcus Vance",
        duckdb_path=Path("var/nonexistent-test-warehouse.duckdb"),
    )

    assert answer["mode"] == "timeline"
    assert answer["entity"] == "Marcus Vance"
    assert answer["results"][0]["source_path"] == "Meetings/Horizon Kickoff.md"


def test_web_ui_answers_summary_question_from_synthetic_vault():
    answer = answer_question(
        Path("examples/synthetic-vault"),
        "summary counts",
        duckdb_path=Path("var/nonexistent-test-warehouse.duckdb"),
    )

    assert answer["mode"] == "summary"
    assert answer["summary"]["tables"]["dim_notes"] == 120


def test_web_ui_suggests_entities_for_unknown_timeline_entity():
    answer = answer_question(
        Path("examples/synthetic-vault"),
        "timeline interactions with Unknown Person",
        duckdb_path=Path("var/nonexistent-test-warehouse.duckdb"),
    )

    assert answer["mode"] == "entity_lookup"
    assert answer["entity"] is None
    assert answer["message"]
    assert answer["results"]


def test_web_ui_groups_requested_entity_types():
    answer = answer_question(
        Path("examples/synthetic-vault"),
        "people companies projects",
        duckdb_path=Path("var/nonexistent-test-warehouse.duckdb"),
    )

    assert answer["mode"] == "entity_groups"
    groups = {group["entity_type"]: group["results"] for group in answer["groups"]}
    assert set(groups) == {"person", "company", "project"}
    assert groups["person"][0]["entity_type"] == "person"
    assert groups["company"][0]["entity_type"] == "company"
    assert groups["project"][0]["entity_type"] == "project"
