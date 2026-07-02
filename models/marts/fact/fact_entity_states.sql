with decision_states as (
  select
    'state:' || entities.entity_id || ':decision_status' as state_id,
    entities.entity_id,
    entities.entity_type,
    entities.name as entity_name,
    'decision_status' as state_type,
    decisions.decision_status as state_value,
    decisions.decision_date as state_date,
    null as severity,
    nullif(split_part(decisions.people, ', ', 1), '') as owner_entity_name,
    decisions.note_id,
    decisions.source_path,
    decisions.title,
    decisions.summary,
    decisions.projects,
    decisions.companies,
    decisions.people
  from {{ ref('fact_decisions') }} decisions
  join {{ ref('dim_entities') }} entities
    on entities.canonical_note_id = decisions.note_id
),

risk_states as (
  select
    'state:' || entities.entity_id || ':risk_status' as state_id,
    entities.entity_id,
    entities.entity_type,
    entities.name as entity_name,
    'risk_status' as state_type,
    risks.risk_status as state_value,
    risks.risk_date as state_date,
    case
      when lower(risks.summary) like '%severity: **high**%' or lower(risks.summary) like '%severity: high%' then 'high'
      when lower(risks.summary) like '%severity: **medium**%' or lower(risks.summary) like '%severity: medium%' then 'medium'
      when lower(risks.summary) like '%severity: **low**%' or lower(risks.summary) like '%severity: low%' then 'low'
      else null
    end as severity,
    nullif(split_part(risks.people, ', ', 1), '') as owner_entity_name,
    risks.note_id,
    risks.source_path,
    risks.title,
    risks.summary,
    risks.projects,
    risks.companies,
    risks.people
  from {{ ref('fact_risks') }} risks
  join {{ ref('dim_entities') }} entities
    on entities.canonical_note_id = risks.note_id
),

combined as (
  select * from decision_states
  union all
  select * from risk_states
)

select
  combined.state_id,
  combined.entity_id,
  combined.entity_type,
  combined.entity_name,
  combined.state_type,
  combined.state_value,
  combined.state_date,
  combined.severity,
  owners.entity_id as owner_entity_id,
  combined.owner_entity_name,
  combined.note_id,
  combined.source_path,
  combined.title,
  combined.summary,
  trim(concat_ws(', ', combined.projects, combined.companies, combined.people), ', ') as related_entities
from combined
left join {{ ref('dim_entities') }} owners
  on owners.entity_type = 'person'
 and lower(owners.name) = lower(combined.owner_entity_name)
