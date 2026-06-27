# obsidian-mcp-context

Turn textual Obsidian vault notes into AI-ready context exposed through MCP.

This project does not run an AI model itself. It parses an Obsidian vault and
exposes structured context to an MCP-aware AI client. The AI client provides the
model; this server provides the vault tools.

## Features

- Obsidian Markdown files (`.md`) by default.
- Optional plain `.txt` parsing as generic text blocks only.
- Synthetic demo vault under `examples/synthetic-vault`.
- Deterministic parsing of headings, heading paths, blocks, tasks, wikilinks, tags, and semantic lines.
- File, block, heading, and line-level provenance.
- CLI and MCP tools for listing notes, searching blocks, listing tasks, and fetching note context.

## How The Pipeline Works

The intended workflow is:

1. You have an Obsidian vault on disk.
2. You install this package locally.
3. You run the MCP server from this repo.
4. Your MCP client connects to that server.
5. The AI client calls tools such as `search_vault_blocks` and `list_vault_tasks`.
6. Each tool call includes a `vault_path`, so the server knows which vault to parse.
7. The server returns structured JSON with source paths, headings, line numbers, blocks, links, tags, and tasks.
8. The AI client uses that returned context to answer questions or help you work with the vault.

The model can be OpenAI, Anthropic, a local model, or anything else supported by
your MCP client. This repo does not currently ask for an API key, configure a
model, create embeddings, or talk to a local LLM directly.

## Install For Local Development

Clone the repo and install it into a virtual environment:

```bash
git clone https://github.com/gavinsomers/obsidian-mcp-context.git
cd obsidian-mcp-context
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

After installation, the local commands are available at:

```bash
.venv/bin/obsidian-mcp-context
.venv/bin/obsidian-mcp-context-mcp
```

## Try The Synthetic Vault

The repo includes a synthetic Obsidian vault at `examples/synthetic-vault`. Use
it first to confirm the parser works before pointing the tools at your own
notes.

List notes:

```bash
.venv/bin/obsidian-mcp-context --vault examples/synthetic-vault notes
```

Search parsed blocks:

```bash
.venv/bin/obsidian-mcp-context --vault examples/synthetic-vault blocks --text renewal
```

List unchecked tasks:

```bash
.venv/bin/obsidian-mcp-context --vault examples/synthetic-vault tasks --unchecked
```

The output is JSON. It is intentionally verbose enough for an AI client to cite
where each piece of context came from.

## Generate Larger Synthetic Vaults

The checked-in `examples/synthetic-vault` remains a compact human-readable
fixture. For scale testing, generate deterministic vaults on demand instead of
committing thousands of Markdown files:

```bash
.venv/bin/obsidian-mcp-context-generate-vault \
  --profile medium \
  --seed 42 \
  --output var/generated-vault \
  --force
```

Development equivalent:

```bash
.venv/bin/python scripts/generate_synthetic_vault.py \
  --profile small \
  --seed 42 \
  --output var/generated-vault \
  --force
```

Profiles:

| Profile | Approximate files | Intended use |
| --- | ---: | --- |
| `small` | 232 | CI-style generated fixture checks |
| `medium` | 1,200 | Local integration and pipeline testing |
| `large` | 5,680 | Stress and performance testing |

Generated vaults include coherent companies, people, projects, meetings,
decisions, risks, research notes, and daily notes. Every generated note includes
virtual lifecycle timestamps:

```yaml
source_created_at: 2025-02-03T09:30:00
source_observed_at: 2025-02-03T10:15:00
created_at: 2025-02-03T14:45:00
updated_at: 2025-02-07T11:20:00
```

Use the generated vault with the same pipeline commands:

```bash
.venv/bin/obsidian-mcp-context-ingest \
  --vault var/generated-vault \
  --duckdb var/generated.duckdb
```

## Simulate A Living Vault With Airflow

The simulation profile models a generated vault being populated over time. The
full seed vault is generated once, then a live vault receives only notes whose
virtual `created_at` date has arrived.

By default, Airflow runs the DAG once per minute. Each run advances the virtual
clock by 12 days, which is equivalent to 1 virtual day every 5 seconds:

```text
60 seconds per Airflow run / 5 seconds per virtual day = 12 virtual days
```

Start the simulation stack:

```bash
docker compose --profile simulation up --build
```

Run it in the background:

```bash
docker compose --profile simulation up --build -d
```

Services:

| Service | URL |
| --- | --- |
| Airflow | `http://localhost:8082` |
| Live vault file browser | `http://localhost:8083` |
| Live vault web UI | `http://localhost:8084` |
| Live vault MCP HTTP endpoint | `http://localhost:8001/mcp` |

Airflow credentials are `admin` / `admin` for the local simulation container.
The MCP endpoint is a machine endpoint for MCP clients, not a browser page. A
normal browser request to `/mcp` may show a protocol/streaming error even when
the service is healthy.

The Airflow DAG is `simulated_daily_obsidian_pipeline` and runs:

```text
ensure seed vault
  -> advance virtual days into /live-vault
  -> ingest /live-vault into DuckDB
  -> dbt run
  -> dbt test
```

Useful simulation environment variables:

```bash
SIM_PROFILE=small                  # small, medium, large
SIM_SEED=42                        # deterministic generated world
SIM_VIRTUAL_DAYS_PER_RUN=12        # 12 days/minute = 5 seconds/day
```

Run one manual advance without Airflow:

```bash
docker compose --profile simulation run --rm seed-vault
docker compose --profile simulation run --rm vault-simulator
```

Reset Docker simulation state:

```bash
docker compose --profile simulation down -v
```

## Docker Compose

Build and run the local stack:

```bash
docker compose up --build
```

Run it in the background:

```bash
docker compose up --build -d
```

Services:

- Web UI: `http://localhost:8080`
- Synthetic vault file browser: `http://localhost:8081`
- MCP streamable HTTP endpoint: `http://localhost:8000/mcp`

Use the web UI and file browser in a normal browser. Use the MCP endpoint only
from an MCP-aware client.

The Compose stack mounts `examples/synthetic-vault` read-only at `/vault`.
Pipeline services write the working dbt warehouse to `var/obsidian.duckdb`.
After successful dbt tests, they publish `var/obsidian-read.duckdb` as the
stable read snapshot used by the web UI and MCP containers.

The `vault` service is an nginx file browser for the synthetic vault contents.
It is not the Obsidian desktop app; the vault remains plain Markdown files so it
can be mounted into containers and opened locally in Obsidian if needed.

Useful local Docker commands:

```bash
docker compose ps
docker compose logs -f
docker compose down
```

## DuckDB And dbt Pipeline

The Docker pipeline can materialize parsed vault context into DuckDB staging
tables and then run dbt models for deterministic dimensions, facts, and marts.

The flow is:

```text
examples/synthetic-vault
  -> obsidian-mcp-context-ingest
  -> DuckDB base_obsidian_* landing tables
  -> dbt run
  -> stg_obsidian_* staging views
  -> int_obsidian_* intermediate models
  -> dim_notes, dim_entities, dim_people, dim_companies, dim_projects
  -> fact_blocks, fact_tasks, fact_links, fact_tags, fact_mentions, fact_decisions, fact_risks
  -> mart_timeline, mart_open_loops, mart_person_context, mart_project_context
  -> dbt test
```

dbt materializations:

| Layer | Materialization |
| --- | --- |
| `stg_obsidian_*` | views |
| `int_obsidian_*` | views |
| `dim_*`, `fact_*`, `mart_*` | incremental tables using DuckDB `merge` |

The public demo intentionally stays Obsidian-only. It does not add source
routing or specialist parsers until additional source families such as WhatsApp,
calendar OCR, Gmail, or CRM exports are introduced. Instead, dbt derives richer
Obsidian marts from deterministic note types, links, tasks, tags, and timeline
rows:

- `dim_people`, `dim_companies`, `dim_projects`
- `fact_mentions`, `fact_decisions`, `fact_risks`
- `mart_open_loops`, `mart_person_context`, `mart_project_context`

When a dbt-built DuckDB warehouse is available at `DUCKDB_PATH` or
`/warehouse/obsidian.duckdb`, the web UI and MCP warehouse tools query these
persisted marts directly. If no dbt warehouse is available, they fall back to
the smaller in-memory warehouse built from the vault files.

In Docker, Airflow and one-off pipeline commands write the primary warehouse at
`/warehouse/obsidian.duckdb`, then atomically publish a successful tested copy
to `/warehouse/obsidian-read.duckdb`. The web UI and MCP containers read that
snapshot by default, which keeps local queries stable while the next pipeline
run is rebuilding the primary DuckDB file.

Run only ingest:

```bash
docker compose --profile pipeline run --rm ingest
```

Run dbt against the ingested DuckDB file:

```bash
docker compose --profile pipeline run --rm dbt
```

Run the full pipeline and checks:

```bash
docker compose --profile pipeline run --rm pipeline
```

That runs ingest, `dbt run`, `dbt test`, pytest, compile checks, and a warehouse
summary smoke test.

The primary DuckDB file is written to `var/obsidian.duckdb`. The tested read
snapshot is written to `var/obsidian-read.duckdb`. Both are ignored by git.

Local equivalents:

```bash
.venv/bin/obsidian-mcp-context-ingest \
  --vault examples/synthetic-vault \
  --duckdb var/obsidian.duckdb

DUCKDB_PATH=var/obsidian.duckdb .venv/bin/dbt run --profiles-dir dbt
DUCKDB_PATH=var/obsidian.duckdb .venv/bin/dbt test --profiles-dir dbt
```

## Use Your Own Obsidian Vault

Find the absolute path to your vault. For example:

```bash
/Users/gavin/Documents/Obsidian/Main Vault
```

or:

```bash
/home/gavman/notes/main-vault
```

Then run the same CLI commands with your vault path:

```bash
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" notes
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" blocks --text "renewal"
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" tasks --unchecked
```

## MCP Server

Start the MCP server manually with:

```bash
.venv/bin/obsidian-mcp-context-mcp
```

Available tools:

- `list_vault_notes`
- `search_vault_blocks`
- `list_vault_tasks`
- `get_vault_note_context`
- `get_vault_warehouse_summary`
- `list_vault_entities`
- `get_vault_entity_timeline`
- `search_vault_agent_context`

Each MCP tool accepts a `vault_path` argument. That means you do not hard-code a
single vault into the server. Your client asks the tool to operate on a specific
vault path.

## Configure An MCP Client

Add this server to your MCP client configuration. Use absolute paths for both
`command` and `cwd`.

```json
{
  "command": "/absolute/path/to/obsidian-mcp-context/.venv/bin/obsidian-mcp-context-mcp",
  "args": [],
  "cwd": "/absolute/path/to/obsidian-mcp-context"
}
```

For this repo checked out at `/home/gavman/code/obsidian-mcp-context`, the
configuration would be:

```json
{
  "command": "/home/gavman/code/obsidian-mcp-context/.venv/bin/obsidian-mcp-context-mcp",
  "args": [],
  "cwd": "/home/gavman/code/obsidian-mcp-context"
}
```

Once the client is connected, ask it to use the tools with your vault path. For
example:

```text
Use the Obsidian MCP context tools with vault_path "/home/gavman/notes/main-vault".
List my unchecked tasks related to renewal.
```

or:

```text
Use vault_path "/home/gavman/notes/main-vault".
Search my vault for blocks about Project Atlas and return the source note and line numbers.
```

## Tool Inputs

`list_vault_notes`

- `vault_path`: path to the Obsidian vault.
- `limit`: maximum notes to return. Defaults to `100`.

`search_vault_blocks`

- `vault_path`: path to the Obsidian vault.
- `text`: optional case-insensitive search text.
- `source_path`: optional filter for vault-relative source paths.
- `heading`: optional filter for heading paths.
- `limit`: maximum blocks to return. Defaults to `25`.

`list_vault_tasks`

- `vault_path`: path to the Obsidian vault.
- `checked`: optional completion filter. Use `false` for open tasks.
- `text`: optional case-insensitive search text.
- `source_path`: optional filter for vault-relative source paths.
- `limit`: maximum tasks to return. Defaults to `50`.

`get_vault_note_context`

- `vault_path`: path to the Obsidian vault.
- `source_path`: vault-relative note path, such as `Projects/Atlas.md`.

`get_vault_warehouse_summary`

- `vault_path`: path to the Obsidian vault.

`list_vault_entities`

- `vault_path`: path to the Obsidian vault.
- `entity_type`: optional filter, such as `person`, `company`, or `project`.
- `text`: optional case-insensitive name filter.
- `limit`: maximum entities to return. Defaults to `100`.

`get_vault_entity_timeline`

- `vault_path`: path to the Obsidian vault.
- `entity`: entity name, such as `Morgan Lee`.
- `text`: optional case-insensitive filter over timeline summaries.
- `limit`: maximum timeline rows to return. Defaults to `50`.

`search_vault_agent_context`

- `vault_path`: path to the Obsidian vault.
- `text`: optional case-insensitive filter over curated context summaries.
- `entity`: optional entity name filter.
- `event_type`: optional event type, such as `block`, `task_open`, or `task_done`.
- `limit`: maximum context rows to return. Defaults to `25`.

When a dbt-built DuckDB warehouse is available, these additional mart-backed
tools are exposed:

`get_vault_project_context`

- `vault_path`: path to the Obsidian vault.
- `project`: exact project name.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum context rows to return. Defaults to `50`.

`get_vault_person_context`

- `vault_path`: path to the Obsidian vault.
- `person`: exact person name.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum context rows to return. Defaults to `50`.

`list_vault_open_loops`

- `vault_path`: path to the Obsidian vault.
- `entity`: optional exact entity name filter.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum open loops to return. Defaults to `50`.

`list_vault_decisions`

- `vault_path`: path to the Obsidian vault.
- `entity`: optional exact entity name filter.
- `status`: optional decision status filter.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum decisions to return. Defaults to `50`.

`list_vault_risks`

- `vault_path`: path to the Obsidian vault.
- `entity`: optional exact entity name filter.
- `status`: optional risk status filter.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum risks to return. Defaults to `50`.

## Deterministic Warehouse Layer

The parser still preserves the vault as the source of truth. On top of that,
the package can query either a persisted dbt DuckDB warehouse or a fallback
in-memory SQLite warehouse so AI clients can query a modeled representation
instead of relying only on semantic recall.

The current warehouse includes:

- `dim_notes`: note type, title, path, absolute path, and source date.
- `dim_entities`: typed entities derived from note folders, wikilinks, and tags.
- `fact_blocks`: parsed Markdown blocks with line-level provenance.
- `fact_tasks`: Markdown tasks with completion state and provenance.
- `fact_links`: wikilinks resolved to modeled entities where possible.
- `fact_tags`: tags as deterministic facts.
- `mart_timeline`: curated block and task rows with dates, entities, and source lines.

Use the CLI to inspect the modeled layer:

```bash
.venv/bin/obsidian-mcp-context --vault examples/synthetic-vault warehouse-summary
.venv/bin/obsidian-mcp-context --vault examples/synthetic-vault entities --entity-type person
.venv/bin/obsidian-mcp-context --vault examples/synthetic-vault timeline --entity "Morgan Lee"
.venv/bin/obsidian-mcp-context --vault examples/synthetic-vault agent-context --entity "Renewal Prep Scope" --event-type task_open
```

## Current AI Boundary

This repo is deliberately model-agnostic right now.

It does:

- Parse local Markdown notes.
- Preserve provenance.
- Return structured context through CLI and MCP tools.
- Build deterministic dimensions, facts, and timeline/context marts in memory.
- Let an MCP client decide how to use that context.

It does not:

- Ask for an OpenAI API key.
- Ask for an Anthropic API key.
- Connect to Ollama or another local model.
- Generate embeddings.
- Store vectors.
- Chat with your notes by itself.
- Persist the warehouse to disk.
- Ingest Gmail, WhatsApp, calendar, CRM, or GitHub data directly.

If you want OpenAI, Anthropic, or local LLM support, configure that in your MCP
client. The client supplies the model; this package supplies the Obsidian vault
context.

## Development

```bash
.venv/bin/python -m pytest
```
