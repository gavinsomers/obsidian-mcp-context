select
  'tag:' || tags.block_id || ':' || tags.line_number || ':' || row_number() over (
    order by tags.source_path, tags.block_id, tags.line_number, tags.tag
  ) as tag_id,
  notes.note_id,
  tags.block_id,
  tags.tag,
  tags.line_number
from {{ ref('stg_obsidian_tags') }} tags
join {{ ref('dim_notes') }} notes
  on notes.source_path = tags.source_path
