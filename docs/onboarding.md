# Bring Your Own Vault

Start with the smallest diagnostic loop, then move into the warehouse and MCP
surfaces when the vault looks healthy.

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
metadata coverage, in-memory warehouse readiness, and optional DuckDB warehouse
readiness.

For personal vault testing, keep the vault outside this repository and add any
local sensitive strings to `.privacy-banned-terms.local`. That file should be
ignored locally through `.git/info/exclude`. Run `scripts/privacy_check.sh`
before committing changes.

## 2. Inspect Parsed Context

```bash
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault notes --limit 20
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault blocks --text renewal
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault tasks --unchecked
```

## 3. Inspect Entities

```bash
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault warehouse-summary
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault entities --limit 50
.venv/bin/obsidian-mcp-context --vault /absolute/path/to/vault agent-context --entity "Acme Renewal"
```

Custom top-level folders such as `Clients/`, `Assets/`, and `Initiatives/`
become generic entity types. See `docs/entity-contract.md` for the full contract.

## 4. Build The DuckDB/dbt Warehouse

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

## Example Vaults

- `examples/minimal-vault`: smallest useful Markdown fixture.
- `examples/custom-entity-vault`: demonstrates custom entity types.
- `examples/synthetic-vault`: larger operator-style demo vault.
