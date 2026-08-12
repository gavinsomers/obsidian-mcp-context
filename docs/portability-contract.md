# Portability Contract

`obsidian-mcp-context` is portable across non-demo Obsidian vaults when the
vault follows a small set of structural conventions or supplies a vault profile
that describes its local conventions. The vault remains the source of truth; the
profile only explains how to interpret folders, note types, and Replay Q&A
wording.

## Generic Behavior

The generic pipeline works without vault-specific code for:

- Markdown notes under scanned folders.
- Obsidian wikilinks such as `[[Account Example]]` and
  `[[Account Example|display text]]`.
- YAML frontmatter parsed as note metadata.
- Top-level folder inference for canonical entity notes.
- Relationship, context, event, and open-loop marts keyed by generic entities.

Vault-specific behavior belongs in a vault profile when folder names or question
vocabulary differ from the built-in demo conventions. Profiles can be checked in
only when they are generic fixtures. Private vault profiles should stay outside
the repo or in ignored local paths. Profile files are schema-checked so unknown
tables and keys fail fast instead of becoming implicit private conventions.

## Folder And Note-Type Inference

The first path segment is the default note-type signal. Built-in folders map to
stable types:

- `people/` -> `person`
- `companies/` -> `company`
- `projects/` -> `project`
- `decisions/` -> `decision`
- `risks/` -> `risk`
- `daily/` -> `daily`
- `meetings/` -> `meeting`
- `research/` -> `research`

Unknown top-level folders become lowercase singular entity types. For example,
`accounts/example_account.md` becomes `account` and
`assets/revenue_model.md` becomes `asset`.

Use `entities.folders` to override that inference when a folder should map to a
different type or to a non-entity note type:

```toml
[entities.folders]
accounts = "account"
cases = "case"
assets = "asset"
meetings = "meeting"
daily = "daily"
```

Use `entities.non_entity_note_types` for note types that provide context but
should not become canonical entities. These notes can still mention entities,
carry tasks, and contribute context rows:

```toml
[entities]
non_entity_note_types = [
  "daily",
  "meeting",
  "note",
  "research",
]
```

Folder mappings are case-insensitive on lookup. Values should be lowercase
singular names. Add explicit mappings when pluralization is ambiguous, a folder
name is domain-specific, or a context folder would otherwise be treated as an
entity type.

## Wikilink And Frontmatter Conventions

Wikilinks are the strongest portable relationship signal. The
[entity contract](entity-contract.md#identity) defines canonical title
precedence, and its [entity sources](entity-contract.md#entity-sources) section
defines supported resolution identities. Prefer human-readable canonical titles
when authoring links; machine-friendly vault-relative paths and filename stems
also resolve. Frontmatter `alias` and `aliases` values preserve alternative
parser and doctor targets, while pipe syntax controls display text:
`[[Example Account|the account]]`.

- Keep canonical entity titles unique across important entity types when
  possible.
- Avoid relying on unresolved wikilinks for production context. They are counted
  and reported, but they cannot provide the same typed context as resolved
  canonical notes.

Frontmatter should use simple YAML values that can be parsed consistently:

- Use ISO dates for date fields.
- Use strings, booleans, numbers, or arrays of strings.
- Use wikilink strings in metadata only when the target note title is still
  clear, such as `account: "[[Example Account]]"`.
- Keep lifecycle or status fields consistent within a note type.

The pipeline does not require a global frontmatter schema for portability, but
consistent names make validation and downstream marts easier to reason about.

## Generic And Typed Surfaces

Portable consumers should prefer generic entity surfaces:

- `dim_entities`
- `dim_entity_types`
- `fact_entity_relationships`
- `fact_entity_states`
- `fact_entity_events`
- `mart_entity_context`
- `mart_entity_open_loops`
- generic entity CLI, API, and MCP tools

Typed convenience marts such as decisions, risks, and open loops remain useful
for common workflows. Project and person surfaces remain compatibility surfaces
for existing consumers. Custom entity types such as `account`, `case`, and
`asset` are supported through generic entity marts and tools; the system does
not automatically create a dedicated typed mart for every custom folder.

## Worked Non-Demo Example

Consider a service vault with these folders:

```text
accounts/
cases/
assets/
meetings/
daily/
```

`accounts`, `cases`, and `assets` are canonical entity folders. `meetings` and
`daily` are context folders. A portable profile for this vault can look like:

```toml
[scan]
include_globs = ["**/*.md"]
exclude_globs = [
  ".git/**",
  ".obsidian/**",
  "templates/**",
  "attachments/**",
]
source_extensions = [".md"]

[entities]
non_entity_note_types = [
  "daily",
  "meeting",
  "note",
  "research",
]

[entities.folders]
accounts = "account"
cases = "case"
assets = "asset"
meetings = "meeting"
daily = "daily"

[replay_qa]
entity_type_preferences = ["account", "case", "asset"]
eval_pack = "/path/to/private-account-eval-pack.json"

[replay_qa.intent_words]
decisions = ["decision", "decisions", "choice", "approval"]
risks = ["risk", "risks", "issue", "issues", "blocker"]
open_loops = ["open", "loop", "loops", "task", "tasks", "todo", "action", "actions"]
timeline = ["timeline", "history", "activity", "sequence"]
```

With that profile:

- `accounts/example_account.md` becomes `entity_type = "account"`.
- `cases/example_case.md` becomes `entity_type = "case"`.
- `assets/example_asset.md` becomes `entity_type = "asset"`.
- `meetings/account_review.md` and `daily/2026-01-15.md` provide context and
  tasks but are not canonical entities.
- Replay Q&A breaks same-name ties in favor of accounts, then cases, then
  assets.
- Replay Q&A routes local words such as `issue` and `action` to the risk and
  open-loop handlers.
- Demo health checks can use a private local eval pack for this vocabulary
  without committing the pack to the repo.

Example portable note content:

```markdown
---
status: active
owner: "[[Example Owner]]"
review_date: 2026-01-31
tags:
  - account
---

# Example Account

Current case: [[Example Case]]

- [ ] Confirm asset inventory for [[Example Asset]].
```

## Validation

Validate portability with generated or synthetic fixtures before using private
vault data in local testing:

```bash
.venv/bin/obsidian-mcp-context \
  --vault examples/generated-vaults/small \
  --vault-profile generated-demo \
  doctor
```

For a private vault, keep the profile and any diagnostic exports out of git:

```bash
.venv/bin/obsidian-mcp-context \
  --vault /path/to/private-vault \
  --vault-profile /path/to/private-profile.toml \
  doctor
```

Recommended checks:

- Run `doctor` and review aggregate counts for ignored files, unsupported files,
  empty notes, large notes, and unresolved wikilinks.
- Run entity listing or context queries against synthetic fixtures first.
- Use `examples/vault-profiles/generated-demo.toml` as the checked-in reference
  for public generated vault conventions.
- Use a private local profile for real vault validation, and do not commit raw
  note content, unresolved-link exports, local vault paths, or screenshots from
  private vaults.
- Use `scripts/check_synthetic_demo.sh --examples /path/to/private-pack.json`
  or a profile-defined `replay_qa.eval_pack` for private/local Q&A evals.
- If a profile is intended for the repo, replace private names with generated
  fixture names and include only synthetic notes.
