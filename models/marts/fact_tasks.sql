{{ config(unique_key='task_id') }}

select
  tasks.task_id,
  notes.note_id,
  tasks.block_id,
  tasks.task_text,
  tasks.checked,
  tasks.line_number,
  tasks.heading,
  tasks.heading_path,
  tasks.block_hash
from {{ ref('stg_obsidian_tasks') }} tasks
join {{ ref('dim_notes') }} notes
  on notes.source_path = tasks.source_path
