select
  'link:' || links.block_id || ':' || links.line_number || ':' || row_number() over (
    order by links.source_path, links.block_id, links.line_number, links.link_target
  ) as link_id,
  notes.note_id,
  links.block_id,
  links.target_entity_id,
  links.link_target,
  links.link_text,
  links.line_number
from {{ ref('int_obsidian_link_resolution') }} links
join {{ ref('dim_notes') }} notes
  on notes.source_path = links.source_path
