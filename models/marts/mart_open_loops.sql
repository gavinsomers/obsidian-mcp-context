{{ config(unique_key='open_loop_id') }}

with task_mentions as (
  select
    tasks.task_id,
    string_agg(distinct mentions.target_name, ', ' order by mentions.target_name) as related_entities,
    string_agg(distinct case when mentions.target_entity_type = 'person' then mentions.target_name end, ', ' order by case when mentions.target_entity_type = 'person' then mentions.target_name end) as people,
    string_agg(distinct case when mentions.target_entity_type = 'company' then mentions.target_name end, ', ' order by case when mentions.target_entity_type = 'company' then mentions.target_name end) as companies,
    string_agg(distinct case when mentions.target_entity_type = 'project' then mentions.target_name end, ', ' order by case when mentions.target_entity_type = 'project' then mentions.target_name end) as projects,
    string_agg(distinct case when mentions.target_entity_type = 'risk' then mentions.target_name end, ', ' order by case when mentions.target_entity_type = 'risk' then mentions.target_name end) as risks
  from {{ ref('fact_tasks') }} tasks
  left join {{ ref('fact_mentions') }} mentions
    on mentions.block_id = tasks.block_id
  where tasks.checked = false
  group by tasks.task_id
)

select
  tasks.task_id as open_loop_id,
  tasks.task_id,
  tasks.note_id,
  notes.note_type as source_note_type,
  notes.title as source_title,
  notes.source_path,
  notes.source_date,
  tasks.block_id,
  tasks.line_number,
  tasks.heading,
  tasks.heading_path,
  tasks.task_text,
  coalesce(task_mentions.related_entities, '') as related_entities,
  coalesce(task_mentions.people, '') as people,
  coalesce(task_mentions.companies, '') as companies,
  coalesce(task_mentions.projects, '') as projects,
  coalesce(task_mentions.risks, '') as risks
from {{ ref('fact_tasks') }} tasks
join {{ ref('dim_notes') }} notes
  on notes.note_id = tasks.note_id
left join task_mentions
  on task_mentions.task_id = tasks.task_id
where tasks.checked = false
