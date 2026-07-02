# Doctor Readiness Report

The `doctor` command produces a privacy-safe readiness report for generated and
local vault workflows. It keeps raw note content out of output unless samples
are explicitly requested.

Run it against the generated demo vault:

```bash
obsidian-mcp-context \
  --vault examples/generated-vaults/large \
  --vault-profile generated-demo \
  doctor
```

For JSON, write reports under ignored `var/`:

```bash
mkdir -p var
VAULT_PATH=examples/generated-vaults/large
obsidian-mcp-context \
  --vault "$VAULT_PATH" \
  --vault-profile generated-demo \
  doctor \
  --json > var/generated-doctor-readiness.json
```

## Readiness Section

The JSON report includes a `readiness` object:

```text
readiness.status
readiness.blocking
readiness.error_count
readiness.warning_count
readiness.blocking_errors
readiness.checks
readiness.suggestions
```

Each check has:

```text
name
status
blocking
message
signals
actions
```

Current checks:

- `profile`
- `vault_access`
- `parser`
- `content`
- `graph`
- `warehouse`
- `dbt`
- `mcp`

Statuses are:

- `ready`: no immediate issue found.
- `warning`: usable, but follow-up is recommended.
- `blocked`: fix before relying on downstream ingest, marts, or MCP.
- `not_checked`: prerequisites are present, but the doctor did not run that
  external step.

The `dbt` check is `not_checked` when the dbt project is present. Run Postgres
ingest and dbt build/test separately for mart-backed readiness.

## Privacy

By default, doctor reports redact samples. Use `--include-samples` only for
local debugging and keep the output under ignored `var/` or outside the
repository.

Unresolved-link exports can include private target names. Write them only to
ignored `var/` or outside the repository:

```bash
obsidian-mcp-context \
  --vault "$VAULT_PATH" \
  --vault-profile generated-demo \
  doctor \
  --export-unresolved var/generated-unresolved-links.json
```
