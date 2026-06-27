select
  note_id,
  source_path,
  absolute_path,
  note_type,
  title,
  source_date,
  source_created_at,
  source_observed_at,
  created_at,
  updated_at
from {{ source('obsidian', 'base_obsidian_files') }}
