# obsidian-mcp-context

Turn generated Obsidian-style vault notes into AI-ready context exposed through
MCP, backed by Postgres and dbt marts.

This project uses generated/synthetic vault fixtures only. Do not use Gavin's
personal Obsidian vault for this workflow.

## Architecture

The supported workflow is:

```text
generated Obsidian vault
  -> container-mounted vault at /vault
  -> Postgres raw landing tables
  -> dbt Postgres marts
  -> MCP consumers
```

Postgres is the canonical warehouse. DuckDB is not part of the supported
project workflow.

## Features

- Generated realistic demo vaults under `examples/generated-vaults`
  (`small`, `medium`, and `large`).
- Deterministic parsing of headings, blocks, tasks, wikilinks, tags, semantic
  lines, and frontmatter.
- Postgres/dbt marts for entities, relationships, states, events, timelines,
  decisions, risks, and open loops.
- MCP tools for mart-backed context retrieval and direct parser diagnostics.
- Containerized Postgres, dbt, dbt docs, Obsidian/webtop, and MCP services.
- Privacy posture that keeps personal vaults out of the project workflow.

## Quickstart

The primary demo path uses only checked-in generated fixtures and the
Postgres/dbt mart workflow.

Install the project:

```bash
git clone https://github.com/gavinsomers/obsidian-mcp-context.git
cd obsidian-mcp-context
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,pipeline]"
```

Run the generated-large Postgres stack end to end and keep it available for
MCP and CLI proof commands:

```bash
ANALYTICS_STACK_KEEP_RUNNING=1 scripts/analytics_stack_check.sh large
```

This builds the required images, starts Postgres, ingests the generated vault,
runs dbt, runs dbt tests, and executes a Postgres-backed MCP smoke check against
the marts.

Check the running demo and canned Q&A examples:

```bash
scripts/check_synthetic_demo.sh
```

The health check validates replay/scheduler state, browser service endpoints,
dashboard readiness, and the generated-demo eval pack in
`examples/eval-packs/generated-demo.json`. Override the pack with
`--examples /path/to/private-eval-pack.json` or select one from a vault profile
with `--vault-profile`.

For the current representative prompt set and demo caveats, see
[docs/retrieval-validation.md](docs/retrieval-validation.md).

Prove the same data is available through an agent-ready preset:

```bash
POSTGRES_DSN=postgresql://obsidian:obsidian@localhost:5432/obsidian_context \
DBT_TARGET_SCHEMA=marts \
.venv/bin/obsidian-mcp-context \
  --vault examples/generated-vaults/large \
  context-preset project_brief \
  --entity "Project Atlas 1" \
  --limit 5
```

The output includes `mode: "mart-backed"`, the preset name, filters, row count,
and source-linked rows from the dbt marts.

List the preset catalogue:

```bash
.venv/bin/obsidian-mcp-context context-presets
```

Run the same stack against smaller fixtures when you want faster smoke checks:

```bash
scripts/analytics_stack_check.sh small
scripts/analytics_stack_check.sh medium
```

Start the complete generated-large browser demo when you want Obsidian/webtop,
Postgres, MCP, Adminer, replay dashboard, Q&A, dbt docs, replay, and scheduler
services together:

```bash
scripts/run_synthetic_demo.sh large
```

For a faster smoke/demo run that loads the full small fixture before the first
ingest/dbt cycle and skips background replay loops:

```bash
scripts/run_synthetic_demo.sh small --fast
```

Stop it with:

```bash
scripts/run_synthetic_demo.sh stop
```

Open the generated-large vault in an isolated browser-accessible Obsidian
container:

```bash
scripts/run_generated_obsidian.sh large
```

Then open `http://localhost:3000`. Obsidian auto-launches in the webtop and
opens the mounted `/vault` folder.

Replay generated-large into an initially empty isolated vault so notes appear
over virtual time:

```bash
scripts/run_generated_replay.sh large --reset --speed 86400 --batch-size 25
```

This mounts `var/replay-vault` into browser Obsidian and copies notes from
`examples/generated-vaults/large` in `created_at` order. Use `--dry-run` to
inspect the replay manifest without copying files.

In a second terminal, refresh Postgres raw tables and dbt marts on a schedule as
the replay vault changes:

```bash
scripts/run_replay_scheduler.sh --interval-seconds 60
```

Use `--once` for a single ingest/dbt cycle. Scheduler state is written to
`var/replay-vault/.obsidian-mcp-scheduler-state.json`.

Open the replay observability dashboard:

```bash
docker compose --env-file .env.analytics.example -f docker-compose.analytics.yml up -d replay-dashboard
```

Then open `http://localhost:8083` to see replay progress, ingest/dbt status,
and current Postgres raw/mart counts.

Keep the generated-large stack running for an MCP client:

```bash
ANALYTICS_STACK_KEEP_RUNNING=1 scripts/analytics_stack_check.sh large
docker compose --env-file .env.analytics.example -f docker-compose.analytics.yml up -d mcp
```

The container MCP endpoint is:

```text
http://localhost:8000
```

Serve dbt lineage and model documentation after building the warehouse:

```bash
docker compose --env-file .env.analytics.example -f docker-compose.analytics.yml up dbt-docs
```

Then open:

```text
http://localhost:8081
```

Inspect live Postgres raw tables and dbt marts in the browser:

```bash
docker compose --env-file .env.analytics.example -f docker-compose.analytics.yml up -d postgres-browser
```

Then open `http://localhost:8082` and log in to Adminer with server
`postgres`, database `obsidian_context`, username `obsidian`, and password
`obsidian`.

For MCP client configuration, see
[docs/mcp-client-setup.md](docs/mcp-client-setup.md).

## Generated Fixtures

| Fixture | Approximate note count | Purpose |
| --- | ---: | --- |
| `examples/generated-vaults/small` | 232 | Fast smoke and demo runs. |
| `examples/generated-vaults/medium` | 1,200 | Development and dashboard testing. |
| `examples/generated-vaults/large` | 5,680 | Scale and performance testing. |

The generated-large fixture includes companies, people, projects, decisions,
risks, meetings, daily notes, research notes, tasks, links, tags, and lifecycle
timestamps.

## MCP Tools

Parser diagnostic tools read parsed Markdown directly:

- `list_vault_notes`
- `search_vault_blocks`
- `list_vault_tasks`
- `get_vault_note_context`

Mart-backed tools read dbt-built Postgres marts:

- `list_vault_context_presets`
- `get_vault_context_preset`
- `get_vault_warehouse_summary`
- `list_vault_entity_types`
- `get_vault_entity_context`
- `list_vault_entity_events`
- `list_vault_entity_relationships`
- `list_vault_entity_states`
- `list_vault_entity_open_loops`
- `get_vault_project_context`
- `get_vault_person_context`
- `list_vault_open_loops`
- `list_vault_decisions`
- `list_vault_risks`

Use `get_vault_context_preset` as the normal agent-facing entry point when a
named bundle such as `project_brief`, `entity_brief`, `decision_log`, or
`risk_register` fits the task. Use lower-level mart tools when a client needs a
specific table-shaped result. Parser tools are diagnostics for source
inspection and troubleshooting.

## Useful Docs

- [Containerized analytics stack](docs/container-stack.md)
- [MCP client setup](docs/mcp-client-setup.md)
- [Architecture](docs/architecture.md)
- [Entity contract](docs/entity-contract.md)
- [Stale context signals](docs/stale-context-signals.md)
- [Configuration](docs/configuration.md)
- [v1.0 release readiness](docs/v1-release-readiness.md)

## Verification

The main end-to-end verification command is:

```bash
scripts/analytics_stack_check.sh large
```

It builds the required images, starts Postgres, ingests the generated vault,
runs dbt, runs dbt tests, and executes a Postgres-backed MCP smoke check against
the marts.

Before recording a demo or preparing marketing screenshots, run the generated
demo health check and full privacy scan:

```bash
scripts/check_synthetic_demo.sh
scripts/privacy_check.sh --all
```

The privacy scan checks tracked files for blocked runtime artifacts and local
sensitive terms from `.privacy-banned-terms.local` when that local-only file is
present.
