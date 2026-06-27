{{ config(unique_key='decision_id') }}

with decision_notes as (
  select *
  from {{ ref('dim_notes') }}
  where note_type = 'decision'
),

decision_text as (
  select
    notes.note_id,
    string_agg(blocks.text, '\n' order by blocks.start_line) as full_text,
    max(case when lower(coalesce(blocks.heading, '')) = 'decision' then blocks.text end) as decision_summary
  from decision_notes notes
  left join {{ ref('fact_blocks') }} blocks
    on blocks.note_id = notes.note_id
  group by notes.note_id
),

decision_mentions as (
  select
    note_id,
    string_agg(distinct case when target_entity_type = 'project' then target_name end, ', ' order by case when target_entity_type = 'project' then target_name end) as projects,
    string_agg(distinct case when target_entity_type = 'company' then target_name end, ', ' order by case when target_entity_type = 'company' then target_name end) as companies,
    string_agg(distinct case when target_entity_type = 'person' then target_name end, ', ' order by case when target_entity_type = 'person' then target_name end) as people
  from {{ ref('fact_mentions') }}
  where target_entity_type in ('project', 'company', 'person')
  group by note_id
)

select
  notes.note_id as decision_id,
  notes.note_id,
  notes.title,
  notes.source_path,
  notes.source_date as decision_date,
  case
    when lower(coalesce(decision_text.full_text, '')) like '%superseded%' then 'superseded'
    when lower(coalesce(decision_text.full_text, '')) like '%approved%' then 'approved'
    else 'active'
  end as decision_status,
  coalesce(decision_text.decision_summary, decision_text.full_text, notes.title) as summary,
  coalesce(decision_mentions.projects, '') as projects,
  coalesce(decision_mentions.companies, '') as companies,
  coalesce(decision_mentions.people, '') as people
from decision_notes notes
left join decision_text
  on decision_text.note_id = notes.note_id
left join decision_mentions
  on decision_mentions.note_id = notes.note_id
