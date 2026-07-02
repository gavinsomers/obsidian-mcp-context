# Generated Vault Onboarding

This project workflow uses generated/synthetic vaults only. Do not use a
personal Obsidian vault for validation or MCP serving.

For the pre-demo privacy checklist, see
[`docs/demo-privacy-readiness.md`](demo-privacy-readiness.md).

## 1. Understand The Demo Shape

The current demo is split across two repositories:

- The generator repo creates the dataset and shows its growth with D3.
- This repo ingests the completed dataset, builds dbt marts, and serves MCP.

For the full runbook, see [`docs/demo-workflow.md`](demo-workflow.md).

## 2. Choose A Fixture

- `examples/generated-vaults/small`: fast smoke checks.
- `examples/generated-vaults/medium`: development checks.
- `examples/generated-vaults/large`: canonical scale and MCP validation.

## 3. Run The Completed-Dataset Workflow

Run the generated-large completed-dataset workflow:

```bash
scripts/run_dataset_workflow.sh large
```

The workflow mounts the generated fixture into the container stack, ingests
parsed rows into Postgres, runs dbt, runs dbt tests, and starts MCP.

For faster checks:

```bash
scripts/run_dataset_workflow.sh small
scripts/run_dataset_workflow.sh medium
```

For generator outputs created outside this repository, import the completed
vault manually into an ignored local path and then pass that path explicitly:

```bash
scripts/run_dataset_workflow.sh var/imported-vaults/generated-current
```

See [`docs/dataset-handoff-contract.md`](dataset-handoff-contract.md) for the
manual generator-to-main handoff contract.

## 4. Use MCP

```bash
scripts/run_dataset_workflow.sh large
```

The workflow leaves the MCP container running at:

```text
http://localhost:8000
```

For client configuration, see `docs/mcp-client-setup.md`.

## 5. Inspect Lineage And Tables

Start inspection surfaces only when you want to show lineage or row-level
evidence:

```bash
scripts/run_dataset_workflow.sh large --with-inspection
```

Open:

```text
dbt Docs:         http://localhost:8081
Postgres browser: http://localhost:8082
```

## 6. Inspect Parser Diagnostics

Parser diagnostics can still inspect generated source files directly:

```bash
.venv/bin/obsidian-mcp-context --vault examples/generated-vaults/large notes --limit 20
.venv/bin/obsidian-mcp-context --vault examples/generated-vaults/large blocks --text Atlas
.venv/bin/obsidian-mcp-context --vault examples/generated-vaults/large tasks --unchecked
```

Use these for troubleshooting only. Mart-backed MCP tools should read from the
Postgres dbt marts.
