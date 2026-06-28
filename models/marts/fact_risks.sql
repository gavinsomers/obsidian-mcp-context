with risk_notes as (
  select *
  from {{ ref('dim_notes') }}
  where note_type = 'risk'
),

risk_text as (
  select
    notes.note_id,
    string_agg(blocks.text, '\n' order by blocks.start_line) as full_text,
    max(case when lower(coalesce(blocks.heading, '')) in ('risk', 'risk summary') then blocks.text end) as risk_summary
  from risk_notes notes
  left join {{ ref('fact_blocks') }} blocks
    on blocks.note_id = notes.note_id
  group by notes.note_id
),

risk_mentions as (
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
  notes.note_id as risk_id,
  notes.note_id,
  notes.title,
  notes.source_path,
  notes.source_date as risk_date,
  case
    when lower(coalesce(risk_text.full_text, '')) like '%resolved%' then 'resolved'
    when lower(coalesce(risk_text.full_text, '')) like '%blocked%' then 'blocked'
    else 'open'
  end as risk_status,
  coalesce(risk_text.risk_summary, risk_text.full_text, notes.title) as summary,
  coalesce(risk_mentions.projects, '') as projects,
  coalesce(risk_mentions.companies, '') as companies,
  coalesce(risk_mentions.people, '') as people
from risk_notes notes
left join risk_text
  on risk_text.note_id = notes.note_id
left join risk_mentions
  on risk_mentions.note_id = notes.note_id
