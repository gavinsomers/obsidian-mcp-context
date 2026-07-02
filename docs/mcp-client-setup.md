# MCP Client Setup For Generated Vaults

This project validates MCP behavior against generated/synthetic vault fixtures
only. Do not point the workflow at a personal Obsidian vault when proving MCP
behavior.

The canonical warehouse is Postgres. DuckDB is not part of the supported MCP
workflow.

The main generated fixture is mounted into the container stack from:

```text
/home/gavman/code/obsidian-mcp-context/examples/generated-vaults/large
```

Inside the containers, the same vault is available at:

```text
/vault
```

## Postgres Container-Backed MCP

Run the completed-dataset workflow. It leaves MCP running after ingest, dbt run,
and dbt tests pass:

```bash
cd /home/gavman/code/obsidian-mcp-context
scripts/run_dataset_workflow.sh large
```

The MCP container reads the Postgres marts with:

```dotenv
WAREHOUSE_BACKEND=postgres
POSTGRES_DSN=postgresql://obsidian:obsidian@postgres:5432/obsidian_context
POSTGRES_WAREHOUSE_SCHEMAS=mart,fact,dim,intermediate,staging
OBSIDIAN_MCP_ALLOWED_ROOTS=/vault
```

The container HTTP endpoint is:

```text
http://localhost:8000
```

## Local Stdio MCP Against Container Postgres

If your MCP client uses stdio, keep the Postgres stack running and configure the
local MCP process to connect to the exposed container database:

```bash
.venv/bin/python -m pip install -e ".[dev,pipeline]"
```

```toml
[mcp_servers.obsidian_generated_large_postgres]
command = "/home/gavman/code/obsidian-mcp-context/.venv/bin/obsidian-mcp-context-mcp"
args = []
cwd = "/home/gavman/code/obsidian-mcp-context"

[mcp_servers.obsidian_generated_large_postgres.env]
WAREHOUSE_BACKEND = "postgres"
POSTGRES_DSN = "postgresql://obsidian:obsidian@localhost:5432/obsidian_context"
POSTGRES_WAREHOUSE_SCHEMAS = "mart,fact,dim,intermediate,staging"
OBSIDIAN_MCP_ALLOWED_ROOTS = "/home/gavman/code/obsidian-mcp-context/examples/generated-vaults"
```

Use this `vault_path` for local stdio MCP calls:

```text
/home/gavman/code/obsidian-mcp-context/examples/generated-vaults/large
```

Use `/vault` only for container-internal checks.

## Prove The Client Is Mart-Backed

These tools prove that the MCP client is reading dbt marts:

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

Recommended proof sequence:

1. Call `get_vault_warehouse_summary` and confirm non-zero mart counts.
2. Call `list_vault_context_presets` and confirm presets such as
   `project_brief`, `entity_brief`, `decision_log`, and `risk_register`.
3. Call `get_vault_context_preset` with `preset="project_brief"` and
   `entity="Project Atlas 1"`, then confirm `mode="mart-backed"` and
   source-linked rows.
4. Call `list_vault_entity_types` and confirm entity types such as `project`,
   `person`, `company`, `decision`, and `risk`.
5. Call `get_vault_entity_context` for `entity_type="project"` and
   `entity="Project Atlas 1"`.
6. Call one relationship, state, or open-loop tool for the same entity.

Parser diagnostic tools are still useful for troubleshooting source Markdown,
but they are not proof of warehouse-backed serving:

- `list_vault_notes`
- `search_vault_blocks`
- `list_vault_tasks`
- `get_vault_note_context`

## Expected Fallback Behavior

If no valid Postgres mart warehouse is available and `WAREHOUSE_BACKEND` is not
set to `postgres`:

- `get_vault_warehouse_summary` returns `warehouse="in_memory_diagnostic"` and
  warning text beginning `No valid dbt warehouse found; falling back to direct
  parser diagnostics`.
- `get_vault_context_preset` returns `mode="parser-diagnostic"` when it cannot
  use marts. Only `recent_context` can return parser diagnostic rows; strict
  mart presets return empty rows with a mart requirement warning.
- Strict mart-only tools such as `list_vault_entity_types`,
  `get_vault_entity_context`, project/person context, decisions, risks, and
  entity open loops return empty results rather than parser data.
- Parser diagnostic tools can still return parsed notes, blocks, and tasks.

This fallback is a diagnostic state, not a successful MCP context setup.

If `WAREHOUSE_BACKEND=postgres` is configured, MCP does not fall back to parsing
the full vault. It raises a clear setup error instead. This keeps the
container-backed workflow from appearing to hang when the local MCP environment
is missing `psycopg`, the database is stopped, or `POSTGRES_DSN` points at the
wrong host.
