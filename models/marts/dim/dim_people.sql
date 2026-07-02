select
  entities.entity_id as person_id,
  entities.name,
  entities.source_path,
  entities.canonical_note_id,
  notes.created_at,
  notes.updated_at
from {{ ref('dim_entities') }} entities
left join {{ ref('dim_notes') }} notes
  on notes.note_id = entities.canonical_note_id
where entities.entity_type = 'person'
