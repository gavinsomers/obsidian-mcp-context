# Changelog

All notable changes to this project are documented here.

The project uses semantic-ish versions:

- Major versions for incompatible parser, warehouse, or MCP contract changes.
- Minor versions for new tools, schema additions, or substantial dataset expansions.
- Patch versions for bug fixes, documentation, and small test updates.

## [Unreleased]

### Added

- Added Dockerfile and Docker Compose stack for the synthetic vault, web UI, MCP HTTP service, and pipeline checks.
- Added `obsidian-mcp-context-web`, a small local web UI over the deterministic warehouse.
- Added MCP server `--host` and `--port` flags for containerized HTTP transports.

## [0.3.0] - 2026-06-27

### Added

- Expanded `examples/synthetic-vault` into a 120-note consultancy operator dataset across May-July 2026.
- Added realistic synthetic people, companies, projects, meetings, decisions, risks, research notes, and daily notes.
- Added multi-month state-change scenarios for:
  - superseded decisions
  - stakeholder sentiment shifts
  - rescheduled meetings
  - task state mutations
- Added `tests/test_synthetic_vault.py` to verify dataset scale and scenario coverage.
- Added live MCP stdio smoke-test coverage during release verification.

### Changed

- Warehouse timeline date derivation now uses frontmatter/content dates when filenames do not contain dates.
- Synthetic vault manifest now tracks target counts, expected queries, and known state-change scenarios.
- Warehouse tests now expect the expanded entity graph.

### Dataset Metrics

- `dim_notes`: 120
- `dim_entities`: 77
- `fact_blocks`: 563
- `fact_tasks`: 185
- `fact_links`: 669
- `fact_tags`: 169
- `mart_timeline`: 748

### Verified

- `.venv/bin/python -m pytest`
- `.venv/bin/python -m compileall obsidian_mcp_context`
- Live MCP stdio smoke test against:
  - `get_vault_warehouse_summary`
  - `list_vault_entities`
  - `get_vault_entity_timeline`
  - `search_vault_agent_context`

## [0.2.0] - 2026-06-27

### Added

- Added an in-memory SQLite warehouse layer derived from parsed vault context.
- Added deterministic dimensions, facts, and marts:
  - `dim_notes`
  - `dim_entities`
  - `fact_blocks`
  - `fact_tasks`
  - `fact_links`
  - `fact_tags`
  - `mart_timeline`
- Added CLI commands:
  - `warehouse-summary`
  - `entities`
  - `timeline`
  - `agent-context`
- Added MCP tools:
  - `get_vault_warehouse_summary`
  - `list_vault_entities`
  - `get_vault_entity_timeline`
  - `search_vault_agent_context`
- Added warehouse-focused tests.

### Changed

- Documented the deterministic warehouse layer and current AI boundary in `README.md`.

### Verified

- `.venv/bin/python -m pytest`
- `.venv/bin/python -m compileall obsidian_mcp_context`
- CLI smoke tests against `examples/synthetic-vault`.

## [0.1.0] - 2026-06-26

### Added

- Initial parser for textual Obsidian vault context.
- CLI and MCP tools for:
  - listing notes
  - searching blocks
  - listing tasks
  - fetching note context
- Markdown parsing for headings, blocks, tasks, wikilinks, tags, and semantic lines.
- Plain text parsing as an opt-in generic text mode.
- Source path, heading, block, line, and hash provenance.
- Initial small synthetic vault.
