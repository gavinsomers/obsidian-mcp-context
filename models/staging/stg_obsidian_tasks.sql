select
  source_path,
  block_id,
  task_id,
  task_text,
  checked,
  line_number,
  heading,
  heading_path,
  block_hash
from {{ source('obsidian', 'base_obsidian_tasks') }}
