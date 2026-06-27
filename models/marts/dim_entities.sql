{{ config(unique_key='entity_id') }}

select
  entity_id,
  entity_type,
  name,
  source_path,
  canonical_note_id
from {{ ref('int_obsidian_entities') }}
