{{ config(unique_key='timeline_id') }}

with block_rows as (
  select
    'block:' || blocks.block_id as timeline_id,
    notes.source_date as event_date,
    'block' as event_type,
    notes.note_id,
    blocks.block_id,
    null as task_id,
    notes.source_path,
    blocks.start_line,
    blocks.end_line,
    coalesce(blocks.heading_path, notes.title) as title,
    blocks.text as summary,
    coalesce(related.related_entities, '') as related_entities
  from {{ ref('fact_blocks') }} blocks
  join {{ ref('dim_notes') }} notes
    on notes.note_id = blocks.note_id
  left join {{ ref('int_obsidian_related_entities') }} related
    on related.block_id = blocks.block_id
  where trim(blocks.text) != ''
),

task_rows as (
  select
    'task:' || tasks.task_id as timeline_id,
    notes.source_date as event_date,
    case when tasks.checked then 'task_done' else 'task_open' end as event_type,
    notes.note_id,
    tasks.block_id,
    tasks.task_id,
    notes.source_path,
    tasks.line_number as start_line,
    tasks.line_number as end_line,
    coalesce(tasks.heading_path, notes.title) as title,
    tasks.task_text as summary,
    coalesce(related.related_entities, '') as related_entities
  from {{ ref('fact_tasks') }} tasks
  join {{ ref('dim_notes') }} notes
    on notes.note_id = tasks.note_id
  left join {{ ref('int_obsidian_related_entities') }} related
    on related.block_id = tasks.block_id
)

select * from block_rows
union all
select * from task_rows
