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
- `mcp`: MCP server container scaffold. Postgres mart reads still need the
  reader adapter described below.
- `ollama` and `enrichment`: optional AI profile scaffold for local enrichment
  work.

DuckDB remains supported for local development. The container stack is the
Postgres path.

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

The intended MCP container contract is `POSTGRES_DSN` plus mart-backed reads from
Postgres. The current public MCP implementation still has its mature DuckDB
reader; Postgres MCP reads are the next adapter step after this stack lands. Do
not treat the `mcp` service as Postgres warehouse-backed until that adapter is
implemented.

AI enrichment should run as an explicit job, not inside ingest or dbt. For local
models, start the AI profile:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml --profile ai up -d ollama
```

The `enrichment` service currently prints a placeholder message. Run a real
enrichment job from that service once the Postgres mart/review adapter is
available.
