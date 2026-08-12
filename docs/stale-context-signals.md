# Stale Context Signals

Stale-context detection is the contract for deciding when MCP-visible memory is
missing, outdated, or unsafe to treat as current. The goal is not to mutate the
vault automatically. The goal is to make stale or missing context visible enough
for a person, dashboard, review queue, or agent workflow to act on it.

The machine-readable catalogue lives in
`obsidian_mcp_context.stale_context.STALE_CONTEXT_SIGNALS`. Dashboard and review
features should consume that catalogue rather than inventing new signal names.

## Signal Status

Signals use three implementation statuses:

- `observable_now`: existing parser, doctor, mart, replay, or dashboard outputs
  already expose enough evidence to report the signal.
- `derivable_now`: existing outputs can support the signal with a small rollup or
  query, but there is not yet a first-class mart or dashboard field.
- `future_model`: the signal is strategically important but needs new modeled
  data, thresholds, review state, or relationship extraction before it should be
  treated as deterministic.

## Initial Catalogue

| Signal ID | Status | Meaning | Current evidence |
| --- | --- | --- | --- |
| `unresolved_wikilinks` | `observable_now` | Wikilinks that do not resolve to scanned note identities. | `doctor.graph.warning_unresolved_wikilinks`, top unresolved targets, path-like reasons. |
| `renamed_or_moved_notes` | `observable_now` | Path-like unresolved links that suggest note titles or folders changed. | Doctor unresolved path-like classifications. |
| `orphaned_references` | `observable_now` | Mentions, links, or tasks point at entities without canonical typed context. | Unresolved wikilinks, `unknown` entities, mentions attached to unknown entities. |
| `stale_open_loops` | `observable_now` | Old unchecked tasks attached to modeled entities. | `mart_entity_open_loops`, `mart_open_loops`, `stale_entities` context preset. |
| `stale_decisions` | `derivable_now` | Superseded, contradicted, or old decisions that need reconfirmation. | `fact_decisions`, decision states, decision dates. |
| `old_project_assumptions` | `future_model` | Old plans, dates, owners, scope, or status statements that may conflict with later context. | Current entity context and decisions can provide evidence, but contradiction/supersession modeling is still needed. |
| `missing_next_actions` | `derivable_now` | Active entities have recent context, open risks, or active decisions but no current next action. | Entity context, open-loop marts, active risks, active decisions. |
| `missing_lifecycle_metadata` | `observable_now` | Notes lack expected lifecycle timestamps or contain malformed timestamp values. | Doctor lifecycle metadata diagnostics. |
| `contextless_notes` | `observable_now` | Empty, unsupported, oversized, or blockless notes cannot provide useful context. | Doctor content diagnostics. |
| `stale_marts` | `observable_now` | Replay, ingest, dbt, or MCP readiness says the warehouse is behind the source vault. | Replay dashboard, scheduler state, pipeline doctor summary. |

## Required Signals From The Strategy

The strategy explicitly called out six stale or missing-context classes:

- Unresolved links: covered by `unresolved_wikilinks`.
- Old project assumptions: covered by `old_project_assumptions`.
- Stale decisions: covered by `stale_decisions`.
- Missing next actions: covered by `missing_next_actions`.
- Renamed notes: covered by `renamed_or_moved_notes`.
- Orphaned references: covered by `orphaned_references`.

## Generated Fixture Expectations

Generated fixtures should remain safe for public tests and demos:

- Generated-large currently has zero unresolved links, so
  `unresolved_wikilinks`, `renamed_or_moved_notes`, and orphaned-link examples
  need targeted synthetic fixtures rather than large-fixture failures.
- Generated fixtures include stale open tasks, so `stale_open_loops` is the
  strongest current demo signal.
- Generated decisions and risks can support `stale_decisions` and
  `missing_next_actions` rollups once thresholds and active-entity rules are
  modeled.
- Replay and scheduler state already support `stale_marts`.

## Design Rules

- Keep the vault as source of truth. Detection should report, queue, or export
  remediation; it should not silently rewrite notes.
- Prefer deterministic evidence first: doctor counts, source-linked marts,
  scheduler state, and explicit review state.
- Make thresholds profile-driven. A weekly project review, monthly account
  review, and yearly archive review should not share one hard-coded definition
  of stale.
- Preserve privacy defaults. Private unresolved-link exports, profile-specific
  thresholds, and real vault names should stay outside the repo.
- Treat parser fallback as diagnostic, not success. Agent-facing stale-context
  checks should say when they are reading marts versus parser diagnostics.

## Downstream Work

Useful follow-up cards can build on this contract:

- Add mart rollups for stale decisions, missing next actions, and entity coverage.
- Add dashboard panels for observable-now signal counts.
- Add review queue state for accepted, rejected, ignored, and deferred freshness
  findings.
- Add profile settings for stale thresholds by entity type and note type.
