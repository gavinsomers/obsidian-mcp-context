from __future__ import annotations

from pathlib import Path

from obsidian_mcp_context.link_review import (
    apply_review_state,
    export_link_suggestion_report,
    load_review_state,
    save_review_decision,
)
from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import (
    build_warehouse,
    list_deterministic_suggested_links,
)


def _suggestion_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "projects").mkdir(parents=True)
    (vault / "daily").mkdir()
    (vault / "projects" / "project_atlas.md").write_text(
        "# Project Atlas\n\n#priority\n", encoding="utf-8"
    )
    (vault / "daily" / "2026-06-28.md").write_text(
        "\n".join(
            [
                "# Daily",
                "",
                "Discussed [[Project Atals]].",
                "#priority",
            ]
        ),
        encoding="utf-8",
    )
    return vault


def _suggestions(vault: Path) -> list[dict[str, object]]:
    context = build_context(VaultConfig(vault_path=vault))
    warehouse = build_warehouse(context)
    return list_deterministic_suggested_links(warehouse, limit=10)


def test_link_review_state_marks_suggestion_accepted(tmp_path: Path):
    suggestions = _suggestions(_suggestion_vault(tmp_path))
    review_path = tmp_path / "review-state.json"
    suggestion_id = str(suggestions[0]["suggestion_id"])

    decision = save_review_decision(
        review_path,
        suggestion_id=suggestion_id,
        status="accepted",
        note="Looks right.",
    )
    reviewed = apply_review_state(
        suggestions,
        load_review_state(review_path),
        status="accepted",
    )

    assert decision.status == "accepted"
    assert reviewed == [
        {
            **suggestions[0],
            "reviewed_status": "accepted",
            "reviewed_at": decision.reviewed_at,
            "review_note": "Looks right.",
        }
    ]


def test_link_review_filters_pending_and_rejected(tmp_path: Path):
    suggestions = _suggestions(_suggestion_vault(tmp_path))
    review_path = tmp_path / "review-state.json"
    rejected_id = str(suggestions[0]["suggestion_id"])
    save_review_decision(
        review_path,
        suggestion_id=rejected_id,
        status="rejected",
    )

    rejected = apply_review_state(
        suggestions,
        load_review_state(review_path),
        status="rejected",
    )
    pending = apply_review_state(
        suggestions,
        load_review_state(review_path),
        status="pending",
    )

    assert [row["suggestion_id"] for row in rejected] == [rejected_id]
    assert rejected_id not in {row["suggestion_id"] for row in pending}


def test_link_review_exports_report_only_payload(tmp_path: Path):
    suggestions = _suggestions(_suggestion_vault(tmp_path))
    review_path = tmp_path / "review-state.json"
    suggestion_id = str(suggestions[0]["suggestion_id"])
    save_review_decision(
        review_path,
        suggestion_id=suggestion_id,
        status="accepted",
    )
    reviewed = apply_review_state(
        suggestions,
        load_review_state(review_path),
        status="accepted",
    )

    report = export_link_suggestion_report(reviewed, status="accepted")

    assert report["mutation_policy"] == "report_only_does_not_modify_vault"
    assert report["count"] == 1
    assert report["proposed_changes"][0]["suggestion_id"] == suggestion_id
    assert report["proposed_changes"][0]["current_target"] == "Project Atals"
    assert report["proposed_changes"][0]["suggested_target"] == "Project Atlas"
