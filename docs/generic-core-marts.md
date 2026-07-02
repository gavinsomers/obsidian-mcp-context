# Generic Core Marts

Generic core marts are the warehouse contract that should work across generated
and other profile-shaped vaults without encoding one vault's conventions as
global defaults.

They describe portable Obsidian-like structure:

- notes
- blocks and semantic lines
- wikilinks and resolved mentions
- tags
- tasks
- entities and entity types
- timeline rows
- active vault profile metadata

## Current Core Contract

Core dimensions:

```text
dim_notes
dim_entities
dim_entity_types
dim_vault_profiles
```

Core facts:

```text
fact_blocks
fact_tasks
fact_links
fact_tags
fact_mentions
```

Core marts:

```text
mart_timeline
```

Typed dimensions and domain facts such as `dim_people`, `dim_companies`,
`dim_projects`, `fact_decisions`, `fact_risks`, `mart_open_loops`,
`mart_entity_open_loops`, and `mart_entity_context` remain useful, but they are
domain marts layered on top of the generic core until their ownership, typed
rollups, and event semantics are fully profile-driven.

## Profile Boundary

The active profile is represented by `dim_vault_profiles`. It contains aggregate
configuration metadata from ingest, including folder mappings, include/exclude
globs, source extensions, non-entity note types, note-type counts, and a profile
fingerprint.

Absolute local paths should remain redacted. Profile-specific meaning should
enter through profile metadata or downstream profile-specific marts, not by
hard-coding private vault assumptions into the generic core.
