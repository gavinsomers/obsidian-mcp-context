with projects as (
  select
    entity_id as project_id,
    name,
    source_path,
    canonical_note_id
  from {{ ref('dim_entities') }}
  where entity_type = 'project'
),

mention_counts as (
  select
    target_entity_id as project_id,
    count(*) as mention_count,
    count(distinct note_id) as mentioned_in_note_count
  from {{ ref('fact_mentions') }}
  where target_entity_type = 'project'
  group by target_entity_id
),

task_counts as (
  select
    mentions.target_entity_id as project_id,
    count(distinct tasks.task_id) as open_task_count
  from {{ ref('fact_mentions') }} mentions
  join {{ ref('fact_tasks') }} tasks
    on tasks.block_id = mentions.block_id
   and tasks.checked = false
  where mentions.target_entity_type = 'project'
  group by mentions.target_entity_id
)

select
  projects.project_id,
  projects.name,
  projects.source_path,
  projects.canonical_note_id,
  notes.created_at,
  notes.updated_at,
  coalesce(mention_counts.mention_count, 0) as mention_count,
  coalesce(mention_counts.mentioned_in_note_count, 0) as mentioned_in_note_count,
  coalesce(task_counts.open_task_count, 0) as open_task_count
from projects
left join {{ ref('dim_notes') }} notes
  on notes.note_id = projects.canonical_note_id
left join mention_counts
  on mention_counts.project_id = projects.project_id
left join task_counts
  on task_counts.project_id = projects.project_id
