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
