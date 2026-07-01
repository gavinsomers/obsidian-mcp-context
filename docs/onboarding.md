# Generated Vault Onboarding

This project workflow uses generated/synthetic vaults only. Do not use a
personal Obsidian vault for validation or MCP serving.

For the pre-demo privacy checklist, see
[`docs/demo-privacy-readiness.md`](demo-privacy-readiness.md).

## 1. Choose A Fixture

- `examples/generated-vaults/small`: fast smoke checks.
- `examples/generated-vaults/medium`: development checks.
- `examples/generated-vaults/large`: canonical scale and MCP validation.

## 2. Run The Postgres Stack

Run the generated-large end-to-end check:

```bash
scripts/analytics_stack_check.sh large
```

The check mounts the generated fixture into the container stack, ingests parsed
rows into Postgres, runs dbt, runs dbt tests, and performs a Postgres-backed MCP
smoke check.

For faster checks:

```bash
scripts/analytics_stack_check.sh small
scripts/analytics_stack_check.sh medium
```

## 3. Keep MCP Running

```bash
ANALYTICS_STACK_KEEP_RUNNING=1 scripts/analytics_stack_check.sh large
docker compose --env-file .env.analytics.example -f docker-compose.analytics.yml up -d mcp
```

The MCP container exposes:

```text
http://localhost:8000
```

For client configuration, see `docs/mcp-client-setup.md`.

## 4. Inspect Diagnostics

Parser diagnostics can still inspect generated source files directly:

```bash
.venv/bin/obsidian-mcp-context --vault examples/generated-vaults/large notes --limit 20
.venv/bin/obsidian-mcp-context --vault examples/generated-vaults/large blocks --text Atlas
.venv/bin/obsidian-mcp-context --vault examples/generated-vaults/large tasks --unchecked
```

Use these for troubleshooting only. Mart-backed MCP tools should read from the
Postgres dbt marts.
