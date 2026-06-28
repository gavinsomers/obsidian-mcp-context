# Local Configuration

`obsidian-mcp-context` can read a local TOML config file for vault-specific scan
and entity behavior. The default path is `.obsidian-mcp-context.toml` in the
current working directory. For personal vault testing, keep that file ignored
locally through `.git/info/exclude`.

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
