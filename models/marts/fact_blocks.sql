{{ config(unique_key='block_id') }}

select
  blocks.block_id,
  notes.note_id,
  blocks.block_hash,
  blocks.heading,
  blocks.heading_path,
  blocks.heading_level,
  blocks.start_line,
  blocks.end_line,
  blocks.text
from {{ ref('stg_obsidian_blocks') }} blocks
join {{ ref('dim_notes') }} notes
  on notes.source_path = blocks.source_path
