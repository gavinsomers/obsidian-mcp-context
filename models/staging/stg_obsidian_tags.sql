select
  source_path,
  block_id,
  tag,
  line_number
from {{ source('obsidian', 'base_obsidian_tags') }}
