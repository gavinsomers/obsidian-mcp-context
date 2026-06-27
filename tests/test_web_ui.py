from pathlib import Path

from obsidian_mcp_context.web_ui import answer_question


def test_web_ui_answers_timeline_question_from_synthetic_vault():
    answer = answer_question(
        Path("examples/synthetic-vault"),
        "timeline interactions with Marcus Vance",
    )

    assert answer["mode"] == "timeline"
    assert answer["entity"] == "Marcus Vance"
    assert answer["results"][0]["source_path"] == "Meetings/Horizon Kickoff.md"


def test_web_ui_answers_summary_question_from_synthetic_vault():
    answer = answer_question(Path("examples/synthetic-vault"), "summary counts")

    assert answer["mode"] == "summary"
    assert answer["summary"]["tables"]["dim_notes"] == 120
