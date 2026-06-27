select
  source_path,
  block_id,
  block_hash,
  heading,
  heading_path,
  heading_level,
  start_line,
  end_line,
  text
from {{ source('obsidian', 'base_obsidian_blocks') }}
