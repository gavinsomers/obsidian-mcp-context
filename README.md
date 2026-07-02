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

Run the quiet completed-dataset workflow when you want to ingest a full
generated vault, build/test dbt marts, and start MCP without Obsidian or replay
services:

```bash
scripts/run_dataset_workflow.sh examples/generated-vaults/large
```

The same command also accepts checked-in fixture shortcuts:

```bash
scripts/run_dataset_workflow.sh small
scripts/run_dataset_workflow.sh medium
scripts/run_dataset_workflow.sh large
```

This validates the selected dataset, starts Postgres, ingests the full vault,
runs dbt, runs dbt tests, and starts MCP at `http://localhost:8000`. It does not
copy data from the generator; pass the generated vault path explicitly after
manually importing or placing it where you want it.

Start lineage and table inspection views only when you want to show them:

```bash
scripts/run_dataset_workflow.sh large --with-inspection
```

That also opens dbt Docs at `http://localhost:8081` and the Postgres table
browser at `http://localhost:8082`. Use `--with-dbt-docs` or
`--with-table-browser` to start only one inspection surface.

Run the generated-large Postgres stack end to end with an MCP smoke check when
you want the older verification command:

```bash
ANALYTICS_STACK_KEEP_RUNNING=1 scripts/analytics_stack_check.sh large
```

This builds the required images, starts Postgres, ingests the generated vault,
runs dbt, runs dbt tests, and executes a Postgres-backed MCP smoke check against
the marts.

Use your MCP client as the primary Q&A surface once the workflow has passed.
Parser diagnostic commands remain available for source inspection, and dbt Docs
or the table browser can be started explicitly when you need lineage or row-level
evidence.

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

Open a generated vault in an isolated browser-accessible Obsidian container only
when you explicitly want to inspect the Markdown vault surface:

```bash
scripts/run_generated_obsidian.sh large
```

Then open `http://localhost:3000`. Obsidian auto-launches in the webtop and
opens the mounted `/vault` folder.

Legacy replay scripts still exist for old virtual-time experiments, but replay,
Replay Q&A, and replay dashboards are no longer part of the main workflow.

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
scripts/run_dataset_workflow.sh large --with-dbt-docs
```

Then open:

```text
http://localhost:8081
```

Inspect live Postgres raw tables and dbt marts in the browser:

```bash
scripts/run_dataset_workflow.sh large --with-table-browser
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
