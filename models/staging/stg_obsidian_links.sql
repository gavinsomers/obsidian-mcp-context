select
  source_path,
  block_id,
  link_target,
  link_text,
  line_number
from {{ source('obsidian', 'base_obsidian_links') }}
