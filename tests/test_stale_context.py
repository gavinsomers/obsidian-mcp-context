from obsidian_mcp_context.stale_context import (
    stale_context_signal_ids,
    stale_context_signals,
)


def test_stale_context_signal_catalogue_includes_strategy_signals():
    signal_ids = set(stale_context_signal_ids())

    assert {
        "unresolved_wikilinks",
        "old_project_assumptions",
        "stale_decisions",
        "missing_next_actions",
        "renamed_or_moved_notes",
        "orphaned_references",
    }.issubset(signal_ids)


def test_stale_context_signals_have_required_metadata():
    signals = stale_context_signals()

    assert len(signals) == len(set(signal["id"] for signal in signals))
    for signal in signals:
        assert signal["id"]
        assert signal["name"]
        assert signal["category"] in {
            "missing_context",
            "pipeline_freshness",
            "stale_assumption",
            "stale_work",
        }
        assert signal["status"] in {
            "derivable_now",
            "future_model",
            "observable_now",
        }
        assert signal["definition"]
        assert signal["current_sources"]
        assert signal["recommended_action"]
        assert signal["default_severity"] in {"error", "info", "warning"}


def test_stale_context_signal_catalogue_marks_currently_observable_sources():
    signals = {signal["id"]: signal for signal in stale_context_signals()}

    assert signals["stale_open_loops"]["status"] == "observable_now"
    assert "mart_entity_open_loops.source_date" in signals["stale_open_loops"][
        "current_sources"
    ]
    assert signals["stale_marts"]["default_severity"] == "error"
