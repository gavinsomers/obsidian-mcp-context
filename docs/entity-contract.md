# Entity Contract

The entity layer turns plain Obsidian notes, wikilinks, and tags into typed,
source-linked rows that can be queried through the CLI, web API, MCP tools, and
dbt marts. The vault remains the source of truth.

## Identity

Every modeled entity has:

- `entity_id`: stable deterministic ID, formatted as `{entity_type}:{slug(name)}`.
- `entity_type`: lowercase singular type, such as `person`, `project`, `client`, or `asset`.
- `name`: display name, usually the note title or tag text.
- `source_path`: vault-relative note path when the entity has a canonical note.
- `canonical_note_id`: note dimension ID when the entity has a canonical note.

For canonical notes, the parsed display title comes from an explicit
frontmatter `title`, then the first level-one heading, then the filename stem.
This keeps machine-friendly filenames such as `morgan_lee.md` separate from the
human-readable entity name.

## Type Inference

Built-in folders map to stable entity or note types:

- `people/` -> `person`
- `companies/` -> `company`
- `projects/` -> `project`
- `decisions/` -> `decision`
- `risks/` -> `risk`
- `daily/` -> `daily`
- `meetings/` -> `meeting`
- `research/` -> `research`

Custom top-level folders become singular entity types. For example:

- `clients/acme_renewal.md` -> `client`
- `assets/revenue_dashboard.md` -> `asset`
- `initiatives/data_trust.md` -> `initiative`

Root-level notes become `note` and are not promoted as canonical entities.
`daily`, `meeting`, `note`, and `research` notes provide context but are not
canonical entities.

## Entity Sources

Canonical note entities come from entity folders. Across parser and warehouse
paths, wikilinks can resolve through a canonical note's parsed title,
vault-relative path, or filename stem. Parser diagnostics and the in-memory
warehouse also recognize frontmatter aliases. Wikilinks without a matching
canonical note become `unknown` entities. Tags become `topic` entities.

## Generic Marts

The generic contract is centered on these marts:

- `dim_entities`: one row per modeled entity.
- `dim_entity_types`: observed entity-type registry with display metadata.
- `fact_entity_relationships`: source-target relationships from note mentions and co-mentions.
- `fact_entity_states`: state rows for stateful modeled notes such as risks and decisions.
- `fact_entity_events`: events attached to any modeled entity.
- `mart_entity_context`: ranked context rows for any modeled entity.
- `mart_entity_open_loops`: unchecked tasks attached to any modeled entity.

Typed marts such as `mart_project_context`, `fact_risks`, and `fact_decisions`
remain compatibility surfaces. New consumers should prefer the generic entity
APIs and MCP tools.

## Freshness And Missing Context

Stale or missing-context detection uses the shared signal catalogue in
[Stale Context Signals](stale-context-signals.md). Generic marts should expose
source-linked evidence that can support those signals, especially unknown or
orphaned references, stale open loops, stale decisions, missing next actions,
and old assumptions that need review.

## Compatibility

The generic entity contract is additive. Existing project, person, risk, and
decision surfaces continue to work. Custom entity types are supported through
generic surfaces only; typed compatibility marts are not created automatically
for every custom type.
