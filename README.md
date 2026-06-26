# obsidian-mcp-context

Turn textual Obsidian vault notes into AI-ready context exposed through MCP.

## Features

- Obsidian Markdown files (`.md`) by default.
- Optional plain `.txt` parsing as generic text blocks only.
- Synthetic demo vault under `examples/synthetic-vault`.
- Deterministic parsing of headings, heading paths, blocks, tasks, wikilinks, tags, and semantic lines.
- File, block, heading, and line-level provenance.
- CLI and MCP tools for listing notes, searching blocks, listing tasks, and fetching note context.

## Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## CLI

```bash
obsidian-mcp-context --vault examples/synthetic-vault notes
obsidian-mcp-context --vault examples/synthetic-vault blocks --text renewal
obsidian-mcp-context --vault examples/synthetic-vault tasks --unchecked
```

## MCP Server

```bash
obsidian-mcp-context-mcp
```

Available tools:

- `list_vault_notes`
- `search_vault_blocks`
- `list_vault_tasks`
- `get_vault_note_context`

Example MCP client command configuration:

```json
{
  "command": "/absolute/path/to/obsidian-mcp-context/.venv/bin/obsidian-mcp-context-mcp",
  "args": [],
  "cwd": "/absolute/path/to/obsidian-mcp-context"
}
```

Each MCP tool accepts a `vault_path` argument so a client can point it at any textual Obsidian vault.

## Development

```bash
pytest
```
