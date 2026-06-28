# Bring Your Own Vault

Start with the smallest diagnostic loop, then build the DuckDB/dbt warehouse.
For real usage, CLI/MCP/web modeled queries should read the curated marts, not
raw parsed Markdown.

## 1. Run Doctor

```bash
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault doctor
```

For CI or scripted checks:

```bash
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault doctor --json
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault doctor --strict
```

Doctor reports parser counts, ignored files, unresolved wikilinks, lifecycle
metadata coverage, direct parser diagnostics, and optional DuckDB warehouse
readiness.

For personal vault testing, keep the vault outside this repository and add any
local sensitive strings to `.privacy-banned-terms.local`. That file should be
ignored locally through `.git/info/exclude`. Run `scripts/privacy_check.sh`
before committing changes.

Use `.obsidian-mcp-context.toml` for local scan excludes and folder-to-entity
overrides. Keep that file ignored locally as well. See `docs/configuration.md`.

## 2. Inspect Parsed Context For Diagnostics

```bash
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault notes --limit 20
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault blocks --text renewal
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault tasks --unchecked
```

These commands parse Markdown directly. Use them to troubleshoot source files,
not as the normal serving path.

## 3. Build The DuckDB/dbt Warehouse

This is a full rebuild flow. The ingest command replaces the `base_obsidian_*`
landing tables from the current vault, and dbt rebuilds marts as tables.

```bash
.venv/bin/obsidian-mcp-context-ingest \
  --vault /absolute/path/to/vault \
  --duckdb var/obsidian.duckdb

DUCKDB_PATH=var/obsidian.duckdb .venv/bin/python -m dbt.cli.main run \
  --profiles-dir dbt \
  --project-dir .

DUCKDB_PATH=var/obsidian.duckdb .venv/bin/python -m dbt.cli.main test \
  --profiles-dir dbt \
  --project-dir .
```

Then validate the persisted warehouse:

```bash
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault doctor --duckdb var/obsidian.duckdb
```

## 4. Query The Marts

```bash
DUCKDB_PATH=var/obsidian.duckdb .venv/bin/obsidian-mcp-context \
  --vault /absolute/path/to/vault warehouse-summary
DUCKDB_PATH=var/obsidian.duckdb .venv/bin/obsidian-mcp-context \
  --vault /absolute/path/to/vault entities --limit 50
DUCKDB_PATH=var/obsidian.duckdb .venv/bin/obsidian-mcp-context \
  --vault /absolute/path/to/vault agent-context --entity "Acme Renewal"
```

Custom top-level folders such as `Clients/`, `Assets/`, and `Initiatives/`
become generic entity types. See `docs/entity-contract.md` for the full contract.

## Example Vaults

- `examples/minimal-vault`: smallest useful Markdown fixture.
- `examples/custom-entity-vault`: demonstrates custom entity types.
- `examples/synthetic-vault`: larger operator-style demo vault.
