select
  note_id,
  source_path,
  absolute_path,
  note_type,
  title,
  source_date
from {{ ref('stg_obsidian_files') }}
