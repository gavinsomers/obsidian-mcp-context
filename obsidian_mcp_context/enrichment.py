from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json

from obsidian_mcp_context.ai import (
    AIProvider,
    AIProviderError,
    ContextOverflowError,
    build_ai_provider,
)
from obsidian_mcp_context.config import AppConfig
from obsidian_mcp_context.warehouse import Warehouse, insert_ai_suggested_link


UNRESOLVED_LINK_PROMPT_VERSION = "unresolved-link-match-v1"
UNRESOLVED_LINK_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_target_note_id": {"type": "string"},
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "maxLength": 80},
    },
    "required": ["selected_target_note_id", "confidence_score", "rationale"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class AIEnrichmentStats:
    calls: int = 0
    skipped_due_to_budget: int = 0
    skipped_due_to_privacy: int = 0
    skipped_due_to_provider_error: int = 0
    skipped_due_to_invalid_candidate: int = 0
    skipped_no_candidate: int = 0
    suggestions_written: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "skipped_due_to_budget": self.skipped_due_to_budget,
            "skipped_due_to_privacy": self.skipped_due_to_privacy,
            "skipped_due_to_provider_error": self.skipped_due_to_provider_error,
            "skipped_due_to_invalid_candidate": self.skipped_due_to_invalid_candidate,
            "skipped_no_candidate": self.skipped_no_candidate,
            "suggestions_written": self.suggestions_written,
        }


def _stats(**overrides: int) -> AIEnrichmentStats:
    values = AIEnrichmentStats().to_dict()
    values.update(overrides)
    return AIEnrichmentStats(**values)


def _add_stats(left: AIEnrichmentStats, right: AIEnrichmentStats) -> AIEnrichmentStats:
    return AIEnrichmentStats(
        **{
            key: left.to_dict()[key] + right.to_dict()[key]
            for key in left.to_dict()
        }
    )


def _deterministic_candidate_rows(warehouse: Warehouse) -> list[dict[str, object]]:
    return warehouse.connection.execute(
        """
        select
            s.source_link_id,
            s.source_note_id,
            source.title as source_title,
            s.link_target,
            s.candidate_target_note_id,
            target.title as candidate_title,
            s.suggestion_type,
            s.deterministic_score,
            s.rank,
            s.signals_json
        from deterministic_suggested_links s
        join dim_notes source on source.note_id = s.source_note_id
        join dim_notes target on target.note_id = s.candidate_target_note_id
        order by s.source_link_id, s.rank
        """
    ).fetchall()


def _prompt_for_candidates(source_link_id: str, rows: list[dict[str, object]]) -> str:
    first = rows[0]
    candidates = [
        {
            "candidate_target_note_id": row["candidate_target_note_id"],
            "candidate_title": row["candidate_title"],
            "deterministic_score": row["deterministic_score"],
            "rank": row["rank"],
            "suggestion_type": row["suggestion_type"],
            "signals": json.loads(str(row["signals_json"])),
        }
        for row in rows
    ]
    payload = {
        "task": "Choose the best existing note for this unresolved wikilink.",
        "rules": [
            "Return only a JSON object.",
            "Use exactly these keys: selected_target_note_id, confidence_score, rationale.",
            "selected_target_note_id must exactly equal one provided candidate_target_note_id value, or an empty string if no candidate fits.",
            "Do not invent target IDs.",
            "confidence_score must be between 0 and 1.",
            "Keep rationale under 8 words.",
            "For weak or ambiguous matches, use rationale: Weak candidate match.",
        ],
        "source_link_id": source_link_id,
        "source_note_title": first["source_title"],
        "link_target": first["link_target"],
        "candidates": candidates,
        "response_schema": {
            "selected_target_note_id": "string",
            "confidence_score": "number from 0 to 1",
            "rationale": "string, max 8 words",
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _confidence(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return 0.0


def run_unresolved_link_ai_enrichment(
    warehouse: Warehouse,
    *,
    config: AppConfig,
    provider: AIProvider | None = None,
) -> AIEnrichmentStats:
    if not config.ai.enabled:
        return AIEnrichmentStats()
    rows = _deterministic_candidate_rows(warehouse)
    if not rows:
        return AIEnrichmentStats()
    if not config.privacy.allow_raw_text_to_ai:
        source_link_count = len({str(row["source_link_id"]) for row in rows})
        return _stats(skipped_due_to_privacy=source_link_count)

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["source_link_id"])].append(row)

    try:
        ai_provider = provider or build_ai_provider(config)
    except AIProviderError:
        return _stats(skipped_due_to_provider_error=len(grouped))

    stats = AIEnrichmentStats()
    for source_link_id, candidate_rows in grouped.items():
        prompt = _prompt_for_candidates(source_link_id, candidate_rows)
        candidate_ids = {
            str(row["candidate_target_note_id"]) for row in candidate_rows
        }
        try:
            result = ai_provider.complete_json(
                prompt,
                UNRESOLVED_LINK_SCHEMA,
                max_context_chars=config.privacy.max_context_chars,
                prompt_version=UNRESOLVED_LINK_PROMPT_VERSION,
            )
        except ContextOverflowError:
            stats = _add_stats(stats, _stats(skipped_due_to_budget=1))
            continue
        except AIProviderError:
            stats = _add_stats(stats, _stats(skipped_due_to_provider_error=1))
            continue

        stats = _add_stats(stats, _stats(calls=1))
        selected = str(result.data.get("selected_target_note_id", "")).strip()
        if not selected:
            stats = _add_stats(stats, _stats(skipped_no_candidate=1))
            continue
        if selected not in candidate_ids:
            stats = _add_stats(stats, _stats(skipped_due_to_invalid_candidate=1))
            continue

        first = candidate_rows[0]
        insert_ai_suggested_link(
            warehouse,
            source_link_id=source_link_id,
            source_note_id=str(first["source_note_id"]),
            suggested_target_note_id=selected,
            suggestion_type="unresolved_link_match",
            confidence_score=_confidence(result.data.get("confidence_score")),
            rationale=str(result.data.get("rationale", ""))[:1000],
            provider=result.provider,
            model=result.model,
            prompt_version=result.prompt_version,
            input_hash=result.input_hash,
            created_at=result.created_at,
            reviewed_status="pending",
        )
        stats = _add_stats(stats, _stats(suggestions_written=1))

    return stats
