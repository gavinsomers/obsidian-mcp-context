# obsidian-mcp-context

Turn textual Obsidian vault notes into AI-ready context exposed through MCP.

This project does not run an AI model itself. It parses an Obsidian vault and
exposes structured context to an MCP-aware AI client. The AI client provides the
model; this server provides the vault tools.

## Features

- Obsidian Markdown files (`.md`) by default.
- Optional plain `.txt` parsing as generic text blocks only.
- Synthetic demo vault under `examples/synthetic-vault`.
- Minimal and custom-entity example vaults under `examples/minimal-vault` and
  `examples/custom-entity-vault`.
- Deterministic parsing of headings, heading paths, blocks, tasks, wikilinks, tags, and semantic lines.
- File, block, heading, and line-level provenance.
- CLI and MCP tools for listing notes, searching blocks, listing tasks, and fetching note context.
- A `doctor` command for parser, graph, metadata, and warehouse readiness checks.

## How The Pipeline Works

For a higher-level view of the runtime services and DuckDB/dbt pipeline, see
[docs/architecture.md](docs/architecture.md).
For the generic entity model, see [docs/entity-contract.md](docs/entity-contract.md).
For the bring-your-own-vault workflow, see [docs/onboarding.md](docs/onboarding.md).
For local scan and entity overrides, see [docs/configuration.md](docs/configuration.md).

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

## Static Fixture Vaults

The checked-in `examples/synthetic-vault` is a compact, human-readable fixture
with coherent companies, people, projects, meetings, decisions, risks, research
notes, and daily notes. It is intentionally static so parser, warehouse, and
reconciliation behavior stays reproducible in this public repo.

Fixture notes include virtual lifecycle timestamps:

```yaml
source_created_at: 2025-02-03T09:30:00
source_observed_at: 2025-02-03T10:15:00
created_at: 2025-02-03T14:45:00
updated_at: 2025-02-07T11:20:00
```

Use the fixture with the same pipeline commands:

```bash
.venv/bin/obsidian-mcp-context-ingest \
  --vault examples/synthetic-vault \
  --duckdb var/obsidian.duckdb
```

## DuckDB And dbt Pipeline

The local pipeline can materialize parsed vault context into DuckDB staging
tables and then run dbt models for deterministic dimensions, facts, and marts.

The flow is:

```text
examples/synthetic-vault
  -> obsidian-mcp-context-ingest
  -> DuckDB base_obsidian_* landing tables
  -> dbt run
  -> stg_obsidian_* staging views
  -> int_obsidian_* intermediate models
  -> dim_notes, dim_entities, dim_entity_types, dim_people, dim_companies, dim_projects
  -> fact_blocks, fact_tasks, fact_links, fact_tags, fact_mentions
  -> fact_entity_relationships, fact_entity_states, fact_entity_events
  -> fact_decisions, fact_risks
  -> mart_timeline, mart_entity_context, mart_entity_open_loops
  -> mart_open_loops, mart_person_context, mart_project_context
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

- Canonical generic tables: `dim_entity_types`, `dim_entities`,
  `fact_entity_relationships`, `fact_entity_states`, `fact_entity_events`,
  `mart_entity_context`, and `mart_entity_open_loops`.
- Compatibility typed marts: `dim_people`, `dim_companies`, `dim_projects`,
  `fact_decisions`, `fact_risks`, `mart_open_loops`, `mart_person_context`,
  and `mart_project_context`.

When a dbt-built DuckDB warehouse is available at `DUCKDB_PATH`, the web UI and
MCP warehouse tools query these persisted marts directly. If no dbt warehouse is
available, they fall back to the smaller in-memory warehouse built from the vault
files.

Run ingest:

```bash
.venv/bin/obsidian-mcp-context-ingest \
  --vault examples/synthetic-vault \
  --duckdb var/obsidian.duckdb
```

Run dbt:

```bash
DUCKDB_PATH=var/obsidian.duckdb .venv/bin/dbt run --profiles-dir dbt
DUCKDB_PATH=var/obsidian.duckdb .venv/bin/dbt test --profiles-dir dbt
```

Run the Python pipeline report:

```bash
.venv/bin/obsidian-mcp-context pipeline run --profile sample
```

Runtime artifacts under `var/` are ignored by git.

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
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" doctor
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" notes
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" blocks --text "renewal"
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" tasks --unchecked
```

For scripted validation, use:

```bash
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" doctor --json
.venv/bin/obsidian-mcp-context --vault "/absolute/path/to/your/vault" doctor --strict
```

Custom top-level folders are promoted to generic entity types. For example,
`Clients/Acme Renewal.md` becomes a `client` entity, while `Assets/Revenue
Dashboard.md` becomes an `asset` entity. See
[docs/entity-contract.md](docs/entity-contract.md) for details.

## MCP Server

Start the MCP server manually with:

```bash
.venv/bin/obsidian-mcp-context-mcp
```

For HTTP transports, restrict readable vault paths with
`OBSIDIAN_MCP_ALLOWED_ROOTS`. It accepts a comma-separated list of absolute
directories. When set, every requested `vault_path` must resolve under one of
those roots:

```bash
OBSIDIAN_MCP_ALLOWED_ROOTS=/home/gavman/notes \
  .venv/bin/obsidian-mcp-context-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Set this environment variable when running the MCP server in HTTP mode against
local vault paths.

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

`list_vault_entity_types`

- `vault_path`: path to the Obsidian vault.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum entity type rows to return. Defaults to `100`.

`get_vault_entity_timeline`

- `vault_path`: path to the Obsidian vault.
- `entity`: entity name, such as `Morgan Lee`.
- `text`: optional case-insensitive filter over timeline summaries.
- `limit`: maximum timeline rows to return. Defaults to `50`.

`get_vault_entity_context`

- `vault_path`: path to the Obsidian vault.
- `entity_type`: exact entity type, such as `project`, `person`, `risk`, or `decision`.
- `entity`: exact entity name.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum context rows to return. Defaults to `50`.

`list_vault_entity_events`

- `vault_path`: path to the Obsidian vault.
- `entity_type`: optional entity type filter.
- `entity`: optional exact entity name filter.
- `event_type`: optional event type filter.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum event rows to return. Defaults to `50`.

`list_vault_entity_relationships`

- `vault_path`: path to the Obsidian vault.
- `entity_type`: optional entity type filter.
- `entity`: optional exact entity name filter.
- `relationship_type`: optional relationship type filter.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum relationship rows to return. Defaults to `50`.

`list_vault_entity_states`

- `vault_path`: path to the Obsidian vault.
- `entity_type`: optional entity type filter.
- `entity`: optional exact entity name filter.
- `state_type`: optional state type filter.
- `status`: optional state value filter.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum state rows to return. Defaults to `50`.

`list_vault_entity_open_loops`

- `vault_path`: path to the Obsidian vault.
- `entity_type`: optional entity type filter.
- `entity`: optional exact entity name filter.
- `duckdb_path`: optional DuckDB warehouse path.
- `limit`: maximum open loops to return. Defaults to `50`.

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
- `dim_entity_types`: observed entity-type registry and type metadata.
- `fact_blocks`: parsed Markdown blocks with line-level provenance.
- `fact_tasks`: Markdown tasks with completion state and provenance.
- `fact_links`: wikilinks resolved to modeled entities where possible.
- `fact_tags`: tags as deterministic facts.
- `fact_entity_relationships`: generic source-target relationships between modeled entities.
- `fact_entity_states`: generic state rows for stateful entities such as risks and decisions.
- `fact_entity_events`: generic event rows attached to any modeled entity.
- `mart_entity_context`: canonical context mart for any typed entity.
- `mart_entity_open_loops`: open loops attached to any typed entity.
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
