# Manual Dataset Handoff Contract

This repository consumes completed generated vaults. It does not ask the
generator to copy, publish, sync, or move datasets into the main workflow
automatically.

The handoff is intentionally manual:

1. Run the generator in the generator repository.
2. Use the generator's D3 view there to watch the dataset grow.
3. When the dataset is complete, ask Codex to import that dataset into this
   repository, or place it yourself in an ignored local path.
4. Run `scripts/run_dataset_workflow.sh` against the imported path.

## Storage Location

Use ignored local storage for manual imports:

```text
var/imported-vaults/<dataset-id>/
```

For the current demo dataset, a convenient path is:

```text
var/imported-vaults/generated-current/
```

The `var/` directory is ignored by git. Do not store personal vault exports,
private client data, or large generated one-off datasets under tracked paths.
Checked-in examples under `examples/generated-vaults/` are intentionally small,
medium, and large synthetic fixtures.

## Completed Vault Layout

The imported directory must be a complete Obsidian-style vault:

```text
var/imported-vaults/<dataset-id>/
  manifest.json
  companies/
  daily/
  decisions/
  meetings/
  people/
  projects/
  research/
  risks/
  ...
```

The workflow requires:

- `manifest.json` at the vault root.
- At least one Markdown note under the vault root.
- Valid JSON in the manifest.
- No dependency on replay state, scheduler state, Obsidian browser state, or
  generator-local D3 state.

The existing workflow accepts current fixture manifests and future generator
manifests. Recommended manifest fields for new generator outputs are:

- `dataset_id`: stable identifier for this completed dataset.
- `schema_version`: version of the generator output contract.
- `generator_version`: generator code or release identifier.
- `created_at`: timestamp when generation completed.
- `completed`: `true` when the dataset is safe to ingest.
- `note_count`: total Markdown note count.
- `entity_counts`: counts by generated domain or entity family.
- `checksum`: optional manifest or dataset checksum for manual verification.

The current checked-in fixtures use fields such as `profile`, `seed`,
`generated_at`, and `counts.Total_Files`; those remain supported.

## Manual Import Procedure

Use an atomic local copy when importing a fresh generator output:

```bash
mkdir -p var/imported-vaults
rm -rf var/imported-vaults/.incoming-generated-current
cp -a /path/to/generator/output/generated-current \
  var/imported-vaults/.incoming-generated-current
mv var/imported-vaults/.incoming-generated-current \
  var/imported-vaults/generated-current
```

If replacing an existing local import, remove or rename the old target first.
The generator still owns dataset creation; this repository only owns ingestion,
dbt transformation, inspection, and MCP serving after a completed dataset path
has been selected.

## Running The Main Workflow

Run the quiet batch workflow against the manually imported path:

```bash
VAULT_PATH=./var/imported-vaults/generated-current \
  docker compose --profile workflow -f docker-compose.analytics.yml run --rm dataset-workflow
```

Start dbt lineage and table inspection only when you need them:

```bash
VAULT_PATH=./var/imported-vaults/generated-current WITH_INSPECTION=1 \
  docker compose --profile workflow -f docker-compose.analytics.yml run --rm dataset-workflow
```

The Compose workflow validates the manifest, counts Markdown notes, starts
Postgres, ingests the whole vault, runs dbt models, runs dbt tests, and starts
MCP. It does not copy from the generator and does not run replay.

Open the optional inspection surfaces after a successful run:

```text
dbt Docs:         http://localhost:8081
Postgres browser: http://localhost:8082
```

Use dbt Docs for model lineage and column documentation. Use the Postgres table
browser for row-level inspection of `raw` landing tables and dbt outputs in
`staging`, `intermediate`, `dim`, `fact`, and `mart`.
