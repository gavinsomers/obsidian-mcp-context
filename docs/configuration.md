# Local Configuration

`obsidian-mcp-context` can read a local TOML config file for vault-specific scan
and entity behavior. The default path is `.obsidian-mcp-context.toml` in the
current working directory. For personal vault testing, keep that file ignored
locally through `.git/info/exclude`.

The same file can also define pipeline source, warehouse, privacy, and AI
profile settings. These settings are read-only config; runtime status and
telemetry should be written under ignored paths such as `var/`, not back into the
TOML file.

You can also pass an explicit path:

```bash
.venv/bin/obsidian-mcp-context \
  --vault /absolute/path/to/vault \
  --config /absolute/path/to/config.toml \
  doctor
```

`doctor` redacts note paths, file paths, and unresolved wikilink targets from
diagnostic samples by default. Aggregate counts remain in the report. For
controlled synthetic-vault debugging, pass `doctor --include-samples` to include
the detailed samples.

Unresolved wikilink reports include aggregate remediation hints such as scan
exclude changes, source extension changes, link path normalization, and missing
note creation. These hints are generated from counts and reason buckets, not raw
target names.

For private local remediation, `doctor` can also write unresolved wikilink
targets to an explicit JSON export:

```bash
mkdir -p var
.venv/bin/obsidian-mcp-context \
  --vault /absolute/path/to/vault \
  --config .obsidian-mcp-context.toml \
  doctor \
  --export-unresolved var/unresolved-links.json
```

The export file may contain private target names from the vault. Keep it local,
write it under an ignored path such as `var/`, and do not commit or paste it into
PRs, issues, docs, or release notes. Source note paths are omitted from the
export unless `doctor --include-samples` is also passed.

## Example

```toml
[source]
type = "sample"
sample_name = "synthetic-vault"
vault_path = ""

[pipeline]
output_dir = "var"
warehouse_path = "var/warehouse.duckdb"
run_mode = "local"

[privacy]
allow_raw_text_to_ai = false
allow_hosted_ai = false
max_context_chars = 1500
redact_file_paths = true

[ai]
enabled = false
provider = "none"
model = ""
base_url = ""
api_key_env = ""

[scan]
extra_exclude_globs = [
  "Imports/**",
  "Attachments/**",
  "OCR/**",
]

[entities]
non_entity_note_types = [
  "daily",
  "meeting",
  "note",
  "research",
  "calendar",
  "archive",
]

[entities.folders]
Clients = "company"
Initiatives = "project"
Assets = "asset"
Calendars = "calendar"

[doctor]
lifecycle_metadata = "warn"
unsupported_files = "warn"
empty_notes = "warn"
large_notes = "warn"
unresolved_wikilinks = "warn"
```

The unresolved wikilink policy also supports a table form when intentional
dangling links should remain counted but stop triggering warnings:

```toml
[doctor.unresolved_wikilinks]
mode = "warn"
ignore_target_globs = [
  "Archive/*",
  "Template:*",
  "Untitled*",
]
```

Additional example profiles live in `examples/config/`.

## Pipeline Profile Settings

- `source.type`: source connector mode. Allowed values are `sample`,
  `obsidian`, and reserved future value `google_drive`.
- `source.sample_name`: sample vault name when `source.type = "sample"`.
- `source.vault_path`: local vault path when `source.type = "obsidian"`.
- `pipeline.output_dir`: ignored runtime output directory. Default: `var`.
- `pipeline.warehouse_path`: DuckDB artifact path. Default:
  `var/warehouse.duckdb`.
- `pipeline.run_mode`: runner mode label. Default: `local`.
- `privacy.allow_raw_text_to_ai`: whether bounded note text may be sent to AI.
  Default: `false`.
- `privacy.allow_hosted_ai`: whether hosted providers may be used. Default:
  `false`.
- `privacy.max_context_chars`: hard context budget for future AI calls. Default:
  `1500`.
- `privacy.redact_file_paths`: whether reports should redact local paths by
  default. Default: `true`.
- `ai.enabled`: enables advisory AI enrichment. Default: `false`.
- `ai.provider`: `none`, `ollama`, `openai`, `anthropic`, or reserved future
  value `vllm`.
- `ai.model`: provider model name.
- `ai.base_url`: local/provider-compatible base URL when needed.
- `ai.api_key_env`: environment variable name containing the API key. Store only
  the env-var name here, never the key value.

Hosted providers such as `openai` and `anthropic` are rejected unless
`privacy.allow_hosted_ai = true`, and they require `ai.api_key_env`.

Environment variables override TOML for CI and local experiments:

- `OBSIDIAN_MCP_SOURCE_TYPE`
- `OBSIDIAN_MCP_AI_ENABLED`
- `OBSIDIAN_MCP_AI_PROVIDER`
- `OBSIDIAN_MCP_AI_MODEL`
- `OBSIDIAN_MCP_AI_BASE_URL`
- `OBSIDIAN_MCP_AI_API_KEY_ENV`

## Pipeline Runner

Run the deterministic pipeline from an explicit config:

```bash
.venv/bin/obsidian-mcp-context pipeline run --config .obsidian-mcp-context.toml
```

Or run one of the checked-in example profiles:

```bash
.venv/bin/obsidian-mcp-context pipeline run --profile sample
```

The runner writes runtime state to `var/pipeline-run.json` by default, or to the
configured `pipeline.output_dir`. The report includes status, source summary,
doctor summary, warehouse summary, AI posture, and suggestion counts. Suggestion
counts include deterministic link suggestions when unresolved wikilinks have
bounded candidate matches.

By default, local source/config paths and doctor samples are redacted from
pipeline output. Use `--include-private-paths` only for local debugging:

```bash
.venv/bin/obsidian-mcp-context pipeline run \
  --config .obsidian-mcp-context.toml \
  --include-private-paths
```

To run doctor against the configured source without passing `--vault`:

```bash
.venv/bin/obsidian-mcp-context pipeline doctor --config .obsidian-mcp-context.toml
```

## Deterministic Suggestions

The warehouse includes a review table named `deterministic_suggested_links`.
Rows are generated without AI for unresolved wikilinks and are advisory until a
human or deterministic rule accepts them.

The current cascade ranks candidates with:

- exact path/title or basename matches
- exact frontmatter alias matches
- bounded string similarity against note titles
- low-confidence shared metadata signals such as overlapping tags

Each suggestion stores the source link, source note, candidate target note,
suggestion type, deterministic score, rank, JSON signals, and creation
timestamp. Pipeline reports surface the row count under
`suggestion_counts.deterministic_suggested_links`.

## Scan Settings

- `scan.include_globs`: replaces the default include globs. Default: `["**/*.md"]`.
- `scan.exclude_globs`: replaces the default exclude globs.
- `scan.extra_exclude_globs`: appends to the default or configured exclude globs.
- `scan.source_extensions`: replaces the default source extensions. Default: `[".md"]`.

## Entity Settings

- `entities.folders`: maps top-level vault folders to note/entity types.
- `entities.non_entity_note_types`: note types that provide context but should not
  become canonical entities.

Folder mappings are case-insensitive on lookup. Values should be lowercase
singular names when they represent entities, such as `client`, `asset`, or
`initiative`.

## Doctor Settings

- `doctor.lifecycle_metadata`: controls lifecycle timestamp diagnostics. Allowed
  values are `warn`, `ignore`, and `error`. Use `ignore` for existing personal
  vaults that do not carry the synthetic lifecycle fields.
- `doctor.ignored_files`, `doctor.unsupported_files`, `doctor.empty_notes`,
  `doctor.notes_without_blocks`, `doctor.large_notes`, and
  `doctor.unresolved_wikilinks`: control the matching warning categories with
  the same `warn`, `ignore`, and `error` modes. Counts remain in the report even
  when a category is ignored.
- `doctor.unresolved_wikilinks.ignore_target_globs`: optional local-only
  patterns for unresolved targets that are expected to remain dangling. Matching
  targets are counted under ignored unresolved aggregate fields and do not
  trigger the unresolved wikilink warning. Keep personal patterns in local config
  only.
