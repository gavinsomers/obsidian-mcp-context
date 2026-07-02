# Containerized Analytics Stack

This mode mirrors a warehouse-first analytics workflow:

```text
Obsidian vault -> Postgres raw schema -> dbt marts -> MCP/web/API consumers
```

Use it when you want the supported analytics-engineering setup with a database
service, dbt container, and editor-visible model code.

## Services

- `vault-obsidian`: full Obsidian desktop in a browser-accessible Linux desktop.
- `postgres`: warehouse database.
- `ingest`: parses the mounted vault and rebuilds `raw.base_obsidian_*`.
- `dbt`: builds staging, intermediate, and mart models into Postgres.
- `dbt-test`: runs dbt tests.
- `dbt-docs-generate`: refreshes dbt docs artifacts, including lineage and
  catalog metadata.
- `dbt-docs`: generates and serves dbt docs in a local browser.
- `postgres-browser`: local Adminer UI for inspecting raw tables and dbt marts.
- `replay-dashboard`: local browser dashboard for replay, scheduler, and
  Postgres mart freshness.
- `mcp`: MCP server container backed by the Postgres dbt marts.
- `ollama` and `enrichment`: optional AI profile scaffold for local enrichment
  work.

Postgres is the canonical warehouse for this project.

## One-Command Check

Run the full synthetic-vault path:

```bash
scripts/analytics_stack_check.sh
```

The check builds the required images, starts Postgres, runs ingest, runs dbt,
runs dbt tests, and executes a Postgres-backed MCP smoke check against the marts.
It uses `.env.analytics` when present, otherwise `.env.analytics.example`.

The repo also includes generated small, medium, and large fixture vaults under
`examples/generated-vaults`. Run the same end-to-end check against one of them:

```bash
scripts/analytics_stack_check.sh small
scripts/analytics_stack_check.sh medium
scripts/analytics_stack_check.sh large
```

This sets `VAULT_PATH` to the selected checked-in generated vault for that run.

## Full Synthetic Demo

Start the complete generated-large replay demo with one command:

```bash
scripts/run_synthetic_demo.sh large
```

For a quick smoke/demo run, use fast mode:

```bash
scripts/run_synthetic_demo.sh small --fast
```

Fast mode preloads all notes from the selected generated fixture before the
first ingest/dbt cycle, runs one scheduler cycle, skips background replay and
scheduler loops, and skips dbt docs. Use the default command when you want to
watch notes arrive over virtual time.

The script accepts `small`, `medium`, or `large`; `large` is the default. It
uses checked-in generated fixtures only, resets the ignored
`var/replay-vault` target by default, starts the browser-accessible services,
loads the first replay notes, runs one ingest/dbt cycle, then starts background
virtual-time replay and ingest/dbt scheduler loops.

Started services:

- `vault-obsidian`
- `postgres`
- `mcp`
- `postgres-browser`
- `replay-dashboard`
- `replay-qa`
- `dbt-docs` unless `--no-dbt-docs` is passed

Useful options:

```bash
scripts/run_synthetic_demo.sh large --no-reset
scripts/run_synthetic_demo.sh small --fast
scripts/run_synthetic_demo.sh large --no-continuous
scripts/run_synthetic_demo.sh large --initial-limit 0 --no-continuous --no-dbt-docs
scripts/run_synthetic_demo.sh large --speed 86400 --batch-size 25 --scheduler-interval 60
scripts/run_synthetic_demo.sh status
scripts/run_synthetic_demo.sh stop
```

Open:

```text
Obsidian webtop:  http://localhost:3000
MCP HTTP:         http://localhost:8000
dbt docs:         http://localhost:8081
Postgres browser: http://localhost:8082
Replay dashboard: http://localhost:8083
Replay Q&A:       http://localhost:8084
```

State and logs:

```text
var/replay-vault/.obsidian-mcp-replay-state.json
var/replay-vault/.obsidian-mcp-scheduler-state.json
logs/synthetic-demo/
var/synthetic-demo/
```

Run the demo health check after startup:

```bash
scripts/check_synthetic_demo.sh
```

It checks local replay and scheduler state, verifies the browser-facing service
ports, reads replay dashboard readiness, and posts the selected eval pack to
Replay Q&A. By default, the generated demo uses
`examples/eval-packs/generated-demo.json`; `--examples` can point at a private
local pack outside the repo, and `--vault-profile` can select a profile-defined
`replay_qa.eval_pack`. Use this when preparing a demo:

```bash
scripts/run_synthetic_demo.sh large
scripts/check_synthetic_demo.sh
```

Useful health-check options:

```bash
scripts/check_synthetic_demo.sh --skip-dbt-docs
scripts/check_synthetic_demo.sh --skip-qa
scripts/check_synthetic_demo.sh --examples /path/to/private-eval-pack.json
scripts/check_synthetic_demo.sh --vault-profile generated-demo
scripts/check_synthetic_demo.sh --json
```

The reset guard refuses to delete targets outside `./var` unless
`DEMO_ALLOW_CUSTOM_RESET=1` is explicitly set. Keep this workflow pointed at
generated fixtures; it does not need Gavin's personal Obsidian vault.

## Browser Obsidian For Generated Vaults

To inspect a generated vault in Obsidian without using a personal vault, start
the browser-accessible Obsidian container:

```bash
scripts/run_generated_obsidian.sh large
```

The script accepts `small`, `medium`, `large`, or `synthetic`; `large` is the
default. It sets `VAULT_PATH` to the selected checked-in fixture and starts only
the isolated `vault-obsidian` service.

Open the webtop session:

```text
http://localhost:3000
```

Obsidian auto-launches in the browser desktop and opens `/vault`. The notes are
mounted from the selected generated fixture folder; they are not imported from,
synced with, or written to Gavin's personal Obsidian vault.

The Obsidian webtop starts Electron with software-rendering defaults
(`--disable-gpu --disable-dev-shm-usage --ozone-platform=x11`) to avoid black
or blank windows in browser-backed desktops. Override `OBSIDIAN_ELECTRON_FLAGS`
only when debugging host-specific rendering behavior.

## Generated Vault Replay

To start with an empty isolated vault and replay generated notes into it over
virtual time, run:

```bash
scripts/run_generated_replay.sh large --reset --speed 86400 --batch-size 25
```

The script accepts `small`, `medium`, or `large`; `large` is the default. It
starts `vault-obsidian` with `var/replay-vault` mounted at `/vault`, then runs
`obsidian-mcp-context-replay-vault` against the selected source fixture. The
default replay order uses note frontmatter `created_at`, falling back to
`source_created_at`, `source_observed_at`, `updated_at`, frontmatter/filename
date, and finally file mtime if needed.

The replay workspace opens Graph view with unresolved nodes hidden. That keeps
future wikilink targets out of the visual graph until their notes are actually
copied into the replay vault.

Useful replay flags:

- `--reset`: clears the isolated target vault before replaying.
- `--dry-run`: prints the sorted manifest summary without copying files.
- `--start` and `--end`: limit the virtual timestamp range.
- `--speed`: virtual seconds advanced per real second; `0` copies the selected
  range immediately.
- `--batch-size`: maximum notes copied per replay tick.
- `--limit`: use the first N sorted notes for smoke checks.

Replay state is written to:

```text
var/replay-vault/.obsidian-mcp-replay-state.json
```

The state file records loaded files, loaded/remaining counts, the current
virtual time, and the latest loaded timestamp. Rerunning without `--reset`
resumes by skipping already loaded files. The source fixture remains read-only
from the replay perspective, and the target is under ignored `var/` storage so
the workflow does not read or write Gavin's personal Obsidian vault.

## Virtual-Time Ingest And dbt Scheduler

Once replay is running, start the scheduler in another terminal to refresh
Postgres and dbt as the target vault changes:

```bash
scripts/run_replay_scheduler.sh --interval-seconds 60
```

The scheduler keeps `VAULT_PATH=./var/replay-vault`, starts Postgres if needed,
then repeatedly runs:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm ingest
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt
```

Use `--once` for a single refresh cycle:

```bash
scripts/run_replay_scheduler.sh --once
```

The default cadence is one run per real minute. You can also set
`REPLAY_SCHEDULER_INTERVAL_SECONDS` before running the script.

Scheduler state is written to:

```text
var/replay-vault/.obsidian-mcp-scheduler-state.json
```

That file records the latest scheduler status, run count, last successful run,
the replay virtual-time watermark seen at the start of each run, loaded and
remaining replay note counts, and captured stdout/stderr tails for ingest and
dbt. The scheduler is single-process, so it never starts a new ingest/dbt cycle
until the previous one has completed. Failed runs are recorded and leave the
last successful marts in Postgres for MCP to continue reading.

## Replay Observability Dashboard

The `replay-dashboard` service exposes a local browser dashboard for the
generated replay environment:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml up -d replay-dashboard
```

Open:

```text
http://localhost:8083
```

The host port is configurable with `REPLAY_DASHBOARD_PORT`. The dashboard reads:

- `var/replay-vault/.obsidian-mcp-replay-state.json`
- `var/replay-vault/.obsidian-mcp-scheduler-state.json`
- Postgres raw table counts from `POSTGRES_RAW_SCHEMA`
- Postgres mart counts from `DBT_TARGET_SCHEMA`

It shows replay virtual time, loaded and remaining note counts, latest scheduler
status, latest successful ingest/dbt run, and whether the current mart state is
ready for MCP-backed browser features. It also summarizes memory-warehouse
observability:

- source vault shape: notes, blocks, tasks, links, tags, lines, and note types
- compiled knowledge shape: entities, entity types, relationships, states,
  events, context rows, timelines, open loops, decisions, risks, and unknown
  entities
- pipeline health: replay state, scheduler state, last scheduler success,
  Postgres availability, MCP mart readiness, and loaded/remaining counts
- suggestion review metrics when review tables are available
- stale-context signal rows from the shared stale-context signal catalogue

Raw and mart table counts remain visible for debugging. The page refreshes
itself every five seconds. It does not expose note content or personal vault
paths.

## Replay Q&A

Start the browser Q&A page:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml up -d replay-qa
```

Open:

```text
http://localhost:8084
```

The page retrieves deterministic context from the current Postgres marts and
keeps the matched rows and source references visible. The `Local Gemma` toggle
adds an optional local Ollama answer-composition step using
`gemma4:26b-a4b-it-q4_K_M` by default. The model receives only the retrieved
rows, source references, and the question; it does not query the vault or
warehouse directly, and it does not write vault notes, warehouse facts, or AI
review tables.

If Ollama is unavailable, returns invalid JSON, or the retrieved evidence exceeds
`REPLAY_QA_SUMMARY_MAX_CONTEXT_CHARS`, the page keeps the deterministic answer
and rows visible. Configure the local model path with:

```dotenv
REPLAY_QA_SUMMARY_MODEL=gemma4:26b-a4b-it-q4_K_M
REPLAY_QA_OLLAMA_BASE_URL=http://host.docker.internal:11434
REPLAY_QA_SUMMARY_MAX_CONTEXT_CHARS=12000
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

The demo and marketing workflow should stay on generated fixtures. For local
experiments outside that workflow, `.env.analytics` can set `VAULT_PATH` to a
private vault path, but those paths, outputs, screenshots, and diagnostics must
stay uncommitted and out of demo material. The same mount path, `/vault`, is
used inside every container.

If the vault uses different folder conventions, provide a vault profile. For a
host-local profile, mount or reference a path visible to the container and set:

```dotenv
OBSIDIAN_MCP_VAULT_PROFILE=/absolute/path/to/vault-profile.toml
```

The profile is loaded before any local `.obsidian-mcp-context.toml` config and
can define scan globs, source extensions, folder-to-entity-type mappings, and
non-entity note types. Checked-in reusable examples live under
`examples/vault-profiles/`; keep private profiles outside the repo unless they
are intentionally generic.

For checked-in generated fixtures, either pass a size to
`scripts/analytics_stack_check.sh` or set `VAULT_PATH` directly:

```dotenv
VAULT_PATH=./examples/generated-vaults/medium
```

## Run The Build

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm ingest
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt-test
```

Refresh dbt docs artifacts after a successful dbt run:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt-docs-generate
```

Open Obsidian through the webtop service:

```text
http://localhost:3000
```

Obsidian auto-launches and opens the mounted `/vault` folder.

## dbt Lineage Docs

The `dbt-docs` service exposes native dbt documentation, including the lineage
graph and model pages. Model pages include column metadata from dbt's catalog
when the warehouse has been built.

Build the warehouse first, then start the docs server:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm ingest
docker compose --env-file .env.analytics -f docker-compose.analytics.yml run --rm dbt
docker compose --env-file .env.analytics -f docker-compose.analytics.yml up dbt-docs
```

Open:

```text
http://localhost:8081
```

The host port is configurable with `DBT_DOCS_PORT`. The service runs
`dbt docs generate` before serving, so the visible lineage and column catalog
reflect the latest successful Postgres dbt state at startup. Restart the service
after later dbt runs to refresh the browser view.

## Postgres Mart Browser

Use `postgres-browser` when you want to inspect actual warehouse rows and
schemas in the browser. It complements dbt docs: dbt docs shows lineage and
model metadata, while Adminer shows the live Postgres tables.

Start it after Postgres has data:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml up -d postgres-browser
```

Open:

```text
http://localhost:8082
```

Log in with:

```text
System: PostgreSQL
Server: postgres
Username: obsidian
Password: obsidian
Database: obsidian_context
```

The host port is configurable with `POSTGRES_BROWSER_PORT`. For demos, inspect
the `marts` schema for dbt outputs and the `raw` schema for landing tables. This
is a local inspection tool, so avoid editing table data unless you are
deliberately testing a database change.

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

For generated-vault-only MCP client setup, including the generated-large HTTP
and stdio examples, see `docs/mcp-client-setup.md`.

AI enrichment should run as an explicit job, not inside ingest or dbt. For local
models, start the AI profile:

```bash
docker compose --env-file .env.analytics -f docker-compose.analytics.yml --profile ai up -d ollama
```

The local demo model target is `gemma4:26b-a4b-it-q4_K_M` through Ollama. Keep
hosted AI disabled for this path; use the checked-in
`examples/config/local-gemma-enrichment.toml` profile for local-only enrichment
experiments outside the critical ingest/dbt/MCP workflow.

The `enrichment` service currently prints a placeholder message. Run a real
enrichment job from that service once the Postgres mart/review adapter is
available.
