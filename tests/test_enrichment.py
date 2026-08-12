from __future__ import annotations

from pathlib import Path

from obsidian_mcp_context.ai import MockProvider
from obsidian_mcp_context.config import AIConfig, AppConfig, PrivacyConfig
from obsidian_mcp_context.enrichment import run_unresolved_link_ai_enrichment
from obsidian_mcp_context.vault import VaultConfig, build_context
from obsidian_mcp_context.warehouse import (
    build_warehouse,
    list_ai_suggested_links,
    list_deterministic_suggested_links,
    warehouse_summary,
)


def _suggestion_warehouse(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "projects").mkdir(parents=True)
    (vault / "daily").mkdir()
    (vault / "projects" / "project_atlas.md").write_text(
        "# Project Atlas\n", encoding="utf-8"
    )
    (vault / "daily" / "2026-06-28.md").write_text(
        "# Daily\n\n[[Project Atals]]\n", encoding="utf-8"
    )
    context = build_context(VaultConfig(vault_path=vault))
    return build_warehouse(context)


def _ai_config(max_context_chars: int = 4000) -> AppConfig:
    return AppConfig(
        privacy=PrivacyConfig(
            allow_raw_text_to_ai=True,
            max_context_chars=max_context_chars,
        ),
        ai=AIConfig(enabled=True, provider="mock"),
    )


def test_ai_enrichment_writes_pending_suggestion_from_candidate_set(tmp_path: Path):
    warehouse = _suggestion_warehouse(tmp_path)
    deterministic = list_deterministic_suggested_links(warehouse, limit=10)
    selected = deterministic[0]["candidate_target_note_id"]
    provider = MockProvider(
        {
            "selected_target_note_id": selected,
            "confidence_score": 0.87,
            "rationale": "Best title match.",
        }
    )

    stats = run_unresolved_link_ai_enrichment(
        warehouse,
        config=_ai_config(),
        provider=provider,
    )

    rows = list_ai_suggested_links(warehouse, limit=10)
    summary = warehouse_summary(warehouse)
    assert stats.calls == 1
    assert stats.suggestions_written == 1
    assert provider.calls == 1
    assert summary["tables"]["ai_suggested_links"] == 1
    assert rows[0]["suggested_target_note_id"] == selected
    assert rows[0]["suggestion_type"] == "unresolved_link_match"
    assert rows[0]["confidence_score"] == 0.87
    assert rows[0]["reviewed_status"] == "pending"
    assert rows[0]["provider"] == "mock"
    assert rows[0]["prompt_version"] == "unresolved-link-match-v1"


def test_ai_enrichment_skips_when_raw_text_to_ai_is_not_allowed(tmp_path: Path):
    warehouse = _suggestion_warehouse(tmp_path)
    provider = MockProvider(
        {
            "selected_target_note_id": "unused",
            "confidence_score": 1,
            "rationale": "unused",
        }
    )
    config = AppConfig(
        privacy=PrivacyConfig(allow_raw_text_to_ai=False),
        ai=AIConfig(enabled=True, provider="mock"),
    )

    stats = run_unresolved_link_ai_enrichment(
        warehouse,
        config=config,
        provider=provider,
    )

    assert stats.skipped_due_to_privacy == 1
    assert stats.calls == 0
    assert provider.calls == 0
    assert list_ai_suggested_links(warehouse) == []


def test_ai_enrichment_rejects_invalid_candidate_id(tmp_path: Path):
    warehouse = _suggestion_warehouse(tmp_path)
    provider = MockProvider(
        {
            "selected_target_note_id": "note:not-a-candidate",
            "confidence_score": 0.99,
            "rationale": "Invented target.",
        }
    )

    stats = run_unresolved_link_ai_enrichment(
        warehouse,
        config=_ai_config(),
        provider=provider,
    )

    assert stats.calls == 1
    assert stats.skipped_due_to_invalid_candidate == 1
    assert stats.suggestions_written == 0
    assert list_ai_suggested_links(warehouse) == []


def test_ai_enrichment_counts_context_budget_skips(tmp_path: Path):
    warehouse = _suggestion_warehouse(tmp_path)
    selected = list_deterministic_suggested_links(warehouse, limit=10)[0][
        "candidate_target_note_id"
    ]
    provider = MockProvider(
        {
            "selected_target_note_id": selected,
            "confidence_score": 0.87,
            "rationale": "Best title match.",
        }
    )

    stats = run_unresolved_link_ai_enrichment(
        warehouse,
        config=_ai_config(max_context_chars=10),
        provider=provider,
    )

    assert stats.skipped_due_to_budget == 1
    assert stats.calls == 0
    assert provider.calls == 0
    assert list_ai_suggested_links(warehouse) == []
