with mention_counts as (
  select
    target_entity_id as person_id,
    count(*) as mention_count,
    count(distinct note_id) as mentioned_in_note_count
  from {{ ref('fact_mentions') }}
  where target_entity_type = 'person'
  group by target_entity_id
),

task_counts as (
  select
    mentions.target_entity_id as person_id,
    count(distinct tasks.task_id) as open_task_count
  from {{ ref('fact_mentions') }} mentions
  join {{ ref('fact_tasks') }} tasks
    on tasks.block_id = mentions.block_id
   and tasks.checked = false
  where mentions.target_entity_type = 'person'
  group by mentions.target_entity_id
)

select
  people.person_id,
  people.name,
  people.source_path,
  people.canonical_note_id,
  people.created_at,
  people.updated_at,
  coalesce(mention_counts.mention_count, 0) as mention_count,
  coalesce(mention_counts.mentioned_in_note_count, 0) as mentioned_in_note_count,
  coalesce(task_counts.open_task_count, 0) as open_task_count
from {{ ref('dim_people') }} people
left join mention_counts
  on mention_counts.person_id = people.person_id
left join task_counts
  on task_counts.person_id = people.person_id
