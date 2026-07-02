select
  links.link_id as mention_id,
  links.note_id,
  notes.note_type as source_note_type,
  notes.title as source_title,
  notes.source_path,
  links.block_id,
  links.line_number,
  links.target_entity_id,
  coalesce(entities.entity_type, 'unknown') as target_entity_type,
  coalesce(entities.name, links.link_target) as target_name,
  blocks.heading,
  blocks.heading_path,
  blocks.text as mention_context
from {{ ref('fact_links') }} links
join {{ ref('dim_notes') }} notes
  on notes.note_id = links.note_id
left join {{ ref('dim_entities') }} entities
  on entities.entity_id = links.target_entity_id
left join {{ ref('fact_blocks') }} blocks
  on blocks.block_id = links.block_id
