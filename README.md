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

Install the project:

```bash
git clone https://github.com/gavinsomers/obsidian-mcp-context.git
cd obsidian-mcp-context
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,pipeline]"
```

Run the generated-large Postgres stack end to end:

```bash
scripts/analytics_stack_check.sh large
```

Run the same check against smaller fixtures:

```bash
scripts/analytics_stack_check.sh small
scripts/analytics_stack_check.sh medium
```

Open the generated-large vault in an isolated browser-accessible Obsidian
container:

```bash
scripts/run_generated_obsidian.sh large
```

Then open `http://localhost:3000` and choose `/vault` inside Obsidian.

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

Use mart-backed tools as the normal serving path. Parser tools are diagnostics
for source inspection and troubleshooting.

## Useful Docs

- [Containerized analytics stack](docs/container-stack.md)
- [MCP client setup](docs/mcp-client-setup.md)
- [Architecture](docs/architecture.md)
- [Entity contract](docs/entity-contract.md)
- [Configuration](docs/configuration.md)

## Verification

The main end-to-end verification command is:

```bash
scripts/analytics_stack_check.sh large
```

It builds the required images, starts Postgres, ingests the generated vault,
runs dbt, runs dbt tests, and executes a Postgres-backed MCP smoke check against
the marts.
