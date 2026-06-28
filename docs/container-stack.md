# Containerized Analytics Stack

This mode mirrors a warehouse-first analytics workflow:

```text
Obsidian vault -> Postgres raw schema -> dbt marts -> MCP/web/API consumers
```

It is separate from the local DuckDB quick path. Use it when you want a more
familiar analytics-engineering setup with a database service, dbt container, and
editor-visible model code.

## Services

- `vault-obsidian`: full Obsidian desktop in a browser-accessible Linux desktop.
- `postgres`: warehouse database.
- `ingest`: parses the mounted vault and rebuilds `raw.base_obsidian_*`.
- `dbt`: builds staging, intermediate, and mart models into Postgres.
- `dbt-test`: runs dbt tests.
- `mcp`: MCP server container backed by the Postgres dbt marts.
- `ollama` and `enrichment`: optional AI profile scaffold for local enrichment
  work.

DuckDB remains supported for local development. The container stack is the
Postgres path.

## One-Command Check

Run the full synthetic-vault path:

```bash
scripts/analytics_stack_check.sh
```

The check builds the required images, starts Postgres, runs ingest, runs dbt,
runs dbt tests, and executes a Postgres-backed MCP smoke check against the marts.
It uses `.env.analytics` when present, otherwise `.env.analytics.example`.

To run the same check against your own vault:

```bash
cp .env.analytics.example .env.analytics
# edit VAULT_PATH=/absolute/path/to/your/vault
scripts/analytics_stack_check.sh
```

By default the script stops the temporary Compose services when it finishes. To
leave Postgres running for inspection:

```bash
ANALYTICS_STACK_KEEP_RUNNING=1 scripts/analytics_stack_check.sh
```

## Vault Selection

The stack uses `VAULT_PATH`.

For the checked-in synthetic fixture:

```bash
cp .env.analytics.example .env.analytics
docker compose --env-file .env.analytics -f docker-compose.analytics.yml up -d postgres vault-obsidian
```

For your own Obsidian vault, edit `.env.analytics`:

```dotenv
VAULT_PATH=/absolute/path/to/your/vault
```

The same mount path, `/vault`, is used inside every container.

## Run The Build

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm ingest
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt-test
```

Open Obsidian through the webtop service:

```text
http://localhost:3000
```

Inside Obsidian, open `/vault`.

## VS Code Workflow

Open the repo normally in VS Code/Cursor and edit:

- `models/staging`
- `models/intermediate`
- `models/marts`
- `models/*/schema.yml`
- `dbt_project.yml`

Then run dbt in the container:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt dbt run --profiles-dir dbt --project-dir .
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt dbt test --profiles-dir dbt --project-dir .
```

The optional devcontainer opens VS Code inside the dbt container while keeping
Postgres and Obsidian running as services.

## MCP And AI Enrichment

The MCP container uses `WAREHOUSE_BACKEND=postgres`, `POSTGRES_DSN`, and
`DBT_TARGET_SCHEMA` to read from the dbt marts in Postgres. Build the warehouse
before starting MCP:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm ingest
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt
docker compose --env-file .env.analytics -f docker-compose.analytics.yml up -d mcp
```

AI enrichment should run as an explicit job, not inside ingest or dbt. For local
models, start the AI profile:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml --profile ai up -d ollama
```

The `enrichment` service currently prints a placeholder message. Run a real
enrichment job from that service once the Postgres mart/review adapter is
available.
