from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable


REVIEW_STATUSES = ("pending", "accepted", "rejected", "ignored")
DEFAULT_REVIEW_STATE_PATH = Path("var/link-suggestion-review-state.json")


@dataclass(frozen=True)
class ReviewDecision:
    suggestion_id: str
    status: str
    reviewed_at: str
    note: str | None = None


def load_review_state(path: Path) -> dict[str, ReviewDecision]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions = payload.get("decisions", {})
    if not isinstance(decisions, dict):
        return {}
    state: dict[str, ReviewDecision] = {}
    for suggestion_id, row in decisions.items():
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "pending"))
        if status not in REVIEW_STATUSES:
            continue
        state[str(suggestion_id)] = ReviewDecision(
            suggestion_id=str(suggestion_id),
            status=status,
            reviewed_at=str(row.get("reviewed_at", "")),
            note=str(row["note"]) if row.get("note") else None,
        )
    return state


def save_review_decision(
    path: Path,
    *,
    suggestion_id: str,
    status: str,
    note: str | None = None,
) -> ReviewDecision:
    if status not in REVIEW_STATUSES or status == "pending":
        raise ValueError("status must be one of: accepted, rejected, ignored")
    state = load_review_state(path)
    decision = ReviewDecision(
        suggestion_id=suggestion_id,
        status=status,
        reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        note=note,
    )
    state[suggestion_id] = decision
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": decision.reviewed_at,
        "decisions": {
            key: {
                "status": value.status,
                "reviewed_at": value.reviewed_at,
                **({"note": value.note} if value.note else {}),
            }
            for key, value in sorted(state.items())
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return decision


def apply_review_state(
    suggestions: Iterable[dict[str, object]],
    state: dict[str, ReviewDecision],
    *,
    status: str = "pending",
) -> list[dict[str, object]]:
    if status not in (*REVIEW_STATUSES, "all"):
        raise ValueError("status must be pending, accepted, rejected, ignored, or all")
    rows: list[dict[str, object]] = []
    for suggestion in suggestions:
        suggestion_id = str(suggestion["suggestion_id"])
        decision = state.get(suggestion_id)
        reviewed_status = decision.status if decision else "pending"
        if status != "all" and reviewed_status != status:
            continue
        rows.append(
            {
                **suggestion,
                "reviewed_status": reviewed_status,
                "reviewed_at": decision.reviewed_at if decision else None,
                "review_note": decision.note if decision else None,
            }
        )
    return rows


def export_link_suggestion_report(
    suggestions: Iterable[dict[str, object]],
    *,
    status: str = "accepted",
) -> dict[str, object]:
    rows = [row for row in suggestions if row.get("reviewed_status") == status]
    return {
        "type": "link_suggestion_review_report",
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mutation_policy": "report_only_does_not_modify_vault",
        "count": len(rows),
        "proposed_changes": [
            {
                "suggestion_id": row["suggestion_id"],
                "source_path": row["source_path"],
                "line_number": row.get("line_number"),
                "current_target": row["link_target"],
                "suggested_target": row["candidate_title"],
                "suggested_target_path": row["candidate_source_path"],
                "suggestion_type": row["suggestion_type"],
                "deterministic_score": row["deterministic_score"],
                "review_note": row.get("review_note"),
                "proposed_edit": (
                    f"Retarget [[{row['link_target']}]] to "
                    f"[[{row['candidate_title']}]]."
                ),
            }
            for row in rows
        ],
    }
