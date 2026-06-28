# Architecture

This project turns a plain-text Obsidian vault into structured, source-linked
context. The vault remains the source of truth. The app can query the vault
directly in memory, or read richer dbt marts from a DuckDB snapshot when the
pipeline has produced one.

## Runtime View

```mermaid
flowchart LR
  user["User or MCP-aware AI client"]
  browser["Browser"]
  mcp_client["MCP client"]
  cli_user["CLI user"]

  vault["Obsidian vault<br/>Markdown and text files"]
  parser["Parser and vault scanner<br/>obsidian_mcp_context.parser/vault"]
  service["ContextService<br/>cache, root validation, dbt fallback"]
  memory["In-memory SQLite warehouse<br/>fallback query path"]

  web["Web UI and JSON API<br/>obsidian-mcp-context-web<br/>:8080"]
  mcp["MCP server<br/>obsidian-mcp-context-mcp<br/>stdio or :8000/mcp"]
  cli["CLI<br/>obsidian-mcp-context"]

  duckdb_read["Stable DuckDB read snapshot<br/>/warehouse/obsidian-read.duckdb"]
  dbt_reader["dbt warehouse reader<br/>obsidian_mcp_context.dbt_warehouse"]

  browser --> web
  user --> browser
  user --> mcp_client
  mcp_client --> mcp
  cli_user --> cli

  web --> service
  mcp --> service
  cli --> parser

  service --> parser
  parser --> vault
  service --> memory
  service --> dbt_reader
  dbt_reader --> duckdb_read
```

The web UI and MCP server share `ContextService`. That service first checks for
a valid dbt-built DuckDB warehouse. If one is available, mart-backed queries use
the stable read snapshot. If not, the service falls back to parsing the vault
and building the smaller in-memory warehouse.

## Pipeline View

```mermaid
flowchart TD
  vault["Obsidian vault<br/>examples/synthetic-vault or mounted vault"]
  ingest["ingest command<br/>obsidian-mcp-context-ingest"]
  writer["DuckDB writer warehouse<br/>/warehouse/obsidian.duckdb"]

  base["base_obsidian_* landing tables<br/>files, blocks, tasks, links, tags, lines"]
  staging["stg_obsidian_* views"]
  intermediate["int_obsidian_* views<br/>entities, link resolution, related entities"]
  marts["dbt marts<br/>dim_*, fact_*, mart_*"]
  tests["dbt test<br/>schema and relationship checks"]
  publish["Atomic publish<br/>copy to temp, then mv"]
  reader["Stable read snapshot<br/>/warehouse/obsidian-read.duckdb"]

  web["Web UI and JSON API"]
  mcp["MCP mart tools"]

  vault --> ingest
  ingest --> writer
  writer --> base
  base --> staging
  staging --> intermediate
  intermediate --> marts
  marts --> tests
  tests --> publish
  publish --> reader
  reader --> web
  reader --> mcp
```

The pipeline writes to the primary DuckDB file and publishes a separate read
snapshot only after dbt succeeds. Long-running web and MCP processes read the
snapshot, so users do not query a half-built warehouse while the next pipeline
run is in progress.

## Mode View

```mermaid
flowchart LR
  subgraph Local["Local development"]
    local_vault["examples/synthetic-vault"]
    local_pipeline["pipeline profile<br/>ingest, dbt run, dbt test, pytest, compileall"]
    local_web["web :8080"]
    local_mcp["mcp :8000/mcp"]
    local_browser["vault browser :8081"]
  end

  subgraph Simulation["Simulation profile"]
    seed["seed-vault generator"]
    live["live vault volume"]
    simulator["vault simulator"]
    airflow["Airflow DAG<br/>simulated_daily_obsidian_pipeline<br/>:8082"]
    live_web["live-web :8084"]
    live_mcp["live-mcp :8001/mcp"]
    live_browser["live-vault browser :8083"]
  end

  local_vault --> local_pipeline
  local_pipeline --> local_web
  local_pipeline --> local_mcp
  local_vault --> local_browser

  seed --> live
  airflow --> simulator
  simulator --> live
  airflow --> live_web
  airflow --> live_mcp
  live --> live_browser
```

Local development uses the checked-in synthetic vault. The simulation profile
creates a seeded vault, advances it over virtual days, and uses Airflow to run
the same ingest and dbt pipeline repeatedly against the live vault volume.

## Main Components

| Component | Role |
| --- | --- |
| `obsidian_mcp_context.parser` and `vault` | Parse Markdown into headings, blocks, tasks, links, tags, semantic lines, and provenance. |
| `obsidian_mcp_context.ingest` | Load parsed vault rows into DuckDB landing tables. |
| `models/staging`, `models/intermediate`, `models/marts` | Transform landing tables into queryable dbt views and incremental mart tables. |
| `obsidian_mcp_context.dbt_warehouse` | Read dbt marts from DuckDB for projects, people, companies, decisions, risks, open loops, and context rows. |
| `obsidian_mcp_context.services` | Shared service layer for web and MCP, including dbt detection and in-memory fallback. |
| `obsidian_mcp_context.web_ui` | Browser UI, question endpoint, status endpoint, and formal JSON API. |
| `obsidian_mcp_context.mcp_server` | MCP tools for notes, blocks, tasks, note context, warehouse summary, entities, project/person context, decisions, risks, and open loops. |
| `obsidian_mcp_context.status` | Runtime status for writer/read warehouses, required marts, row counts, and simulation state. |
| `obsidian_mcp_context.synthetic` and `simulator` | Deterministic demo-vault generation and live-vault advancement for testing. |

## Primary Data Contracts

| Layer | Important Outputs |
| --- | --- |
| Landing tables | `base_obsidian_files`, `base_obsidian_blocks`, `base_obsidian_tasks`, `base_obsidian_links`, `base_obsidian_tags`, `base_obsidian_lines` |
| Staging views | `stg_obsidian_files`, `stg_obsidian_blocks`, `stg_obsidian_tasks`, `stg_obsidian_links`, `stg_obsidian_tags`, `stg_obsidian_lines` |
| Intermediate views | `int_obsidian_entities`, `int_obsidian_link_resolution`, `int_obsidian_related_entities` |
| Core marts | `dim_notes`, `dim_entities`, `dim_people`, `dim_companies`, `dim_projects` |
| Fact marts | `fact_blocks`, `fact_tasks`, `fact_links`, `fact_tags`, `fact_mentions`, `fact_decisions`, `fact_risks` |
| Context marts | `mart_timeline`, `mart_open_loops`, `mart_person_context`, `mart_project_context` |

## Query Surfaces

| Surface | Examples |
| --- | --- |
| CLI | `obsidian-mcp-context --vault ... notes`, `blocks`, `tasks`, `warehouse-summary`, `agent-context` |
| MCP | `list_vault_notes`, `search_vault_blocks`, `get_vault_project_context`, `list_vault_risks` |
| Web UI | Browser query interface and pipeline status panel |
| JSON API | `/api/projects`, `/api/projects/{project}/context`, `/api/risks?status=open`, `/api/open-loops` |
