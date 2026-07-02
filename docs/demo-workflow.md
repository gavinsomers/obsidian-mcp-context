# Demo Workflow

The current demo is a two-act workflow:

```text
Act 1: generator repo
  generate synthetic vault
  show dataset growth in D3

manual handoff
  copy completed vault into ignored local storage

Act 2: obsidian-mcp-context
  ingest completed vault
  run dbt models and tests
  serve MCP from dbt marts
  open dbt Docs or table browser only on demand
```

Do not use Obsidian, replay, scheduler windows, or replay Q&A for the primary
demo. Those remain legacy inspection tools for old virtual-time experiments.

## Act 1: Generate And Visualize

Run the generator from the generator repository:

```bash
cd /home/gavman/code/obsidian-mcp-context-generator
.venv/bin/obsidian-mcp-context-generate-vault \
  --profile large \
  --seed 42 \
  --output var/generated-vault \
  --force
```

Open the D3 growth dashboard against that generated vault:

```bash
.venv/bin/obsidian-mcp-context-growth-dashboard \
  --vault var/generated-vault \
  --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

The dashboard reads the generator's `generation-events.jsonl` and manifest
snapshot files. It is the visual surface for dataset growth.

## Manual Handoff

The generator does not copy data into this repository automatically. When the
dataset is complete, import it manually into ignored local storage:

```bash
cd /home/gavman/code/obsidian-mcp-context
mkdir -p var/imported-vaults
rm -rf var/imported-vaults/.incoming-generated-current
cp -a /home/gavman/code/obsidian-mcp-context-generator/var/generated-vault \
  var/imported-vaults/.incoming-generated-current
rm -rf var/imported-vaults/generated-current
mv var/imported-vaults/.incoming-generated-current \
  var/imported-vaults/generated-current
```

For the full contract, see
[`docs/dataset-handoff-contract.md`](dataset-handoff-contract.md).

## Act 2: Build Marts And Serve MCP

Run the quiet completed-dataset workflow against the manually imported vault:

```bash
VAULT_PATH=./var/imported-vaults/generated-current \
  docker compose --profile workflow -f docker-compose.analytics.yml run --rm dataset-workflow
```

This validates the dataset, starts Postgres, ingests the complete vault, runs
dbt models, runs dbt tests, and starts MCP at:

```text
http://localhost:8000
```

Use an MCP client for Q&A against the dbt-built marts. Parser commands are
diagnostics, not the main demo surface.

## Optional Proof Surfaces

Start both optional inspection views only when you want proof:

```bash
VAULT_PATH=./var/imported-vaults/generated-current WITH_INSPECTION=1 \
  docker compose --profile workflow -f docker-compose.analytics.yml run --rm dataset-workflow
```

Open:

```text
dbt Docs:         http://localhost:8081
Postgres browser: http://localhost:8082
```

Use dbt Docs for model lineage and column documentation. Use the Postgres table
browser for raw table and mart row inspection.

For faster local smoke checks, use the checked-in fixture shortcut:

```bash
scripts/run_dataset_workflow.sh small --with-inspection
```
