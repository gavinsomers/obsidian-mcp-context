select
  source_path,
  block_id,
  line_number,
  heading,
  heading_path,
  text
from {{ source('obsidian', 'base_obsidian_lines') }}
