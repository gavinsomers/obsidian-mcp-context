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

## Docker Compose

Build and run the local stack:

```bash
docker compose up --build
```

Services:

- Web UI: `http://localhost:8080`
- Synthetic vault file browser: `http://localhost:8081`
- MCP streamable HTTP endpoint: `http://localhost:8000/mcp`

The Compose stack mounts `examples/synthetic-vault` read-only at `/vault` in the
Python services. The web UI and MCP server both build the deterministic
warehouse from that mounted vault.

Run the pipeline checks in Docker:

```bash
docker compose --profile check run --rm pipeline
```

That runs:

```bash
python -m pytest
python -m compileall obsidian_mcp_context
obsidian-mcp-context --vault /vault warehouse-summary
```

The `vault` service is an nginx file browser for the synthetic vault contents.
It is not the Obsidian desktop app; the vault remains plain Markdown files so it
can be mounted into containers and opened locally in Obsidian if needed.

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

## Deterministic Warehouse Layer

The parser still preserves the vault as the source of truth. On top of that,
the package now builds an in-memory SQLite warehouse so AI clients can query a
modeled representation instead of relying only on semantic recall.

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
