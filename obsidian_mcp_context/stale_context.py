from __future__ import annotations


STALE_CONTEXT_SIGNALS: tuple[dict[str, object], ...] = (
    {
        "id": "unresolved_wikilinks",
        "name": "Unresolved wikilinks",
        "category": "missing_context",
        "status": "observable_now",
        "definition": (
            "Wikilinks that do not resolve to scanned note titles, after local ignore "
            "patterns are applied."
        ),
        "current_sources": [
            "doctor.graph.warning_unresolved_wikilinks",
            "doctor.graph.top_unresolved_targets",
            "doctor.graph.unresolved_path_like_reasons",
        ],
        "future_sources": [
            "deterministic link suggestion review state",
            "AI link suggestion review state",
        ],
        "recommended_action": (
            "Create the missing note, retarget the link, add an intentional ignore "
            "pattern, or review a deterministic suggestion."
        ),
        "default_severity": "warning",
    },
    {
        "id": "renamed_or_moved_notes",
        "name": "Renamed or moved notes",
        "category": "missing_context",
        "status": "observable_now",
        "definition": (
            "Path-like unresolved wikilinks or missing source references that suggest a "
            "note title or folder changed without updating inbound links."
        ),
        "current_sources": [
            "doctor.graph.unresolved_path_like_reasons",
            "doctor.graph.warning_unresolved_path_like_reasons",
        ],
        "future_sources": [
            "accepted link suggestion audit trail",
            "note rename/move manifest if a vault supplies one",
        ],
        "recommended_action": (
            "Retarget stale links to the current canonical note or add an explicit "
            "alias when the old name remains meaningful."
        ),
        "default_severity": "warning",
    },
    {
        "id": "orphaned_references",
        "name": "Orphaned references",
        "category": "missing_context",
        "status": "observable_now",
        "definition": (
            "Mentions, wikilinks, or tasks that point at entities without canonical "
            "notes or typed context."
        ),
        "current_sources": [
            "doctor.graph.warning_unresolved_wikilinks",
            "dim_entities where entity_type = 'unknown'",
            "fact_mentions rows attached to unknown entities",
        ],
        "future_sources": [
            "entity coverage score by note type",
            "review queue for unknown entity promotion",
        ],
        "recommended_action": (
            "Promote important unknown entities to canonical notes or deliberately "
            "exclude low-value references from context workflows."
        ),
        "default_severity": "warning",
    },
    {
        "id": "stale_open_loops",
        "name": "Stale open loops",
        "category": "stale_work",
        "status": "observable_now",
        "definition": (
            "Unchecked tasks attached to modeled entities whose source date or note "
            "lifecycle timestamp is older than the review threshold."
        ),
        "current_sources": [
            "mart_entity_open_loops.source_date",
            "mart_open_loops.source_date",
            "context preset stale_entities",
        ],
        "future_sources": [
            "profile-specific stale-open-loop threshold",
            "accepted/rejected freshness review state",
        ],
        "recommended_action": (
            "Resolve, reassign, rewrite, or explicitly defer old open loops so agents "
            "do not treat stale work as current intent."
        ),
        "default_severity": "warning",
    },
    {
        "id": "stale_decisions",
        "name": "Stale decisions",
        "category": "stale_assumption",
        "status": "derivable_now",
        "definition": (
            "Decision rows that are superseded, contradicted by later context, or old "
            "enough to require reconfirmation for the entity they affect."
        ),
        "current_sources": [
            "fact_decisions.decision_status",
            "fact_decisions.decision_date",
            "fact_entity_states where entity_type = 'decision'",
        ],
        "future_sources": [
            "profile-specific decision review threshold",
            "supersedes/superseded-by relationship model",
        ],
        "recommended_action": (
            "Mark superseded decisions clearly, link replacement decisions, or record "
            "a fresh confirmation note."
        ),
        "default_severity": "warning",
    },
    {
        "id": "old_project_assumptions",
        "name": "Old project assumptions",
        "category": "stale_assumption",
        "status": "future_model",
        "definition": (
            "Statements about plans, dates, ownership, scope, or status that were true "
            "at the time of writing but may conflict with later events or decisions."
        ),
        "current_sources": [
            "mart_entity_context.event_date",
            "fact_entity_events.event_date",
            "fact_decisions.decision_date",
        ],
        "future_sources": [
            "assumption extraction model",
            "contradiction/supersession relationships",
            "profile-specific review thresholds by entity type",
        ],
        "recommended_action": (
            "Capture replacement context as a dated decision, state update, or note "
            "that explicitly supersedes the old assumption."
        ),
        "default_severity": "info",
    },
    {
        "id": "missing_next_actions",
        "name": "Missing next actions",
        "category": "missing_context",
        "status": "derivable_now",
        "definition": (
            "Important active entities that have recent context, risks, or decisions "
            "but no current open loop or next-action task."
        ),
        "current_sources": [
            "mart_entity_context",
            "mart_entity_open_loops",
            "fact_risks where risk_status = 'open'",
            "fact_decisions where decision_status = 'active'",
        ],
        "future_sources": [
            "entity activity rollup mart",
            "profile-specific active entity rules",
        ],
        "recommended_action": (
            "Add an explicit next action, owner, or waiting state for the entity so an "
            "agent can distinguish active work from passive history."
        ),
        "default_severity": "warning",
    },
    {
        "id": "missing_lifecycle_metadata",
        "name": "Missing lifecycle metadata",
        "category": "missing_context",
        "status": "observable_now",
        "definition": (
            "Notes missing expected lifecycle timestamps, making freshness and replay "
            "ordering less reliable."
        ),
        "current_sources": [
            "doctor.content.missing_lifecycle_field_count",
            "doctor.content.malformed_lifecycle_field_count",
        ],
        "future_sources": [
            "profile-specific lifecycle field requirements by note type",
        ],
        "recommended_action": (
            "Add or normalize lifecycle fields for notes that should participate in "
            "freshness, replay, or dated context workflows."
        ),
        "default_severity": "warning",
    },
    {
        "id": "contextless_notes",
        "name": "Contextless notes",
        "category": "missing_context",
        "status": "observable_now",
        "definition": (
            "Empty notes, notes without parsed blocks, unsupported files, or oversized "
            "notes that are unlikely to produce useful agent context."
        ),
        "current_sources": [
            "doctor.content.empty_notes",
            "doctor.content.notes_without_blocks",
            "doctor.content.unsupported_files",
            "doctor.content.large_notes",
        ],
        "future_sources": [
            "profile-specific note-type coverage expectations",
        ],
        "recommended_action": (
            "Fill, exclude, split, or convert source files so expected context is "
            "available to parser and mart workflows."
        ),
        "default_severity": "warning",
    },
    {
        "id": "stale_marts",
        "name": "Stale marts",
        "category": "pipeline_freshness",
        "status": "observable_now",
        "definition": (
            "Replay, ingest, dbt, or MCP readiness state indicates the warehouse is "
            "behind the vault source."
        ),
        "current_sources": [
            "replay_dashboard.status",
            "replay_scheduler state",
            "pipeline doctor summary",
        ],
        "future_sources": [
            "vault mtime versus mart build watermark",
            "dashboard freshness signal rollup",
        ],
        "recommended_action": (
            "Run ingest/dbt, inspect scheduler failures, or mark agent answers as stale "
            "until the latest successful marts catch up."
        ),
        "default_severity": "error",
    },
)


def stale_context_signals() -> list[dict[str, object]]:
    return [dict(signal) for signal in STALE_CONTEXT_SIGNALS]


def stale_context_signal_ids() -> tuple[str, ...]:
    return tuple(str(signal["id"]) for signal in STALE_CONTEXT_SIGNALS)
