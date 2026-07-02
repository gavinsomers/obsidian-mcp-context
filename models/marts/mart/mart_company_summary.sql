with mention_counts as (
  select
    target_entity_id as company_id,
    count(*) as mention_count,
    count(distinct note_id) as mentioned_in_note_count
  from {{ ref('fact_mentions') }}
  where target_entity_type = 'company'
  group by target_entity_id
),

task_counts as (
  select
    mentions.target_entity_id as company_id,
    count(distinct tasks.task_id) as open_task_count
  from {{ ref('fact_mentions') }} mentions
  join {{ ref('fact_tasks') }} tasks
    on tasks.block_id = mentions.block_id
   and tasks.checked = false
  where mentions.target_entity_type = 'company'
  group by mentions.target_entity_id
)

select
  companies.company_id,
  companies.name,
  companies.source_path,
  companies.canonical_note_id,
  companies.created_at,
  companies.updated_at,
  coalesce(mention_counts.mention_count, 0) as mention_count,
  coalesce(mention_counts.mentioned_in_note_count, 0) as mentioned_in_note_count,
  coalesce(task_counts.open_task_count, 0) as open_task_count
from {{ ref('dim_companies') }} companies
left join mention_counts
  on mention_counts.company_id = companies.company_id
left join task_counts
  on task_counts.company_id = companies.company_id
