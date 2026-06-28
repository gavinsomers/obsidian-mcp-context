with expected(decision_name, sponsor_name, project_name) as (
  values
    ('Horizon CFO Sponsorship Update', 'Marcus Vance', 'Project Horizon')
),
actual as (
  select distinct
    decision_relationships.source_entity_name as decision_name,
    sponsor_relationships.target_entity_name as sponsor_name,
    decision_relationships.target_entity_name as project_name
  from fact_entity_relationships decision_relationships
  join fact_entity_relationships sponsor_relationships
    on sponsor_relationships.source_entity_type = 'decision'
   and sponsor_relationships.source_entity_name = decision_relationships.source_entity_name
   and sponsor_relationships.target_entity_type = 'person'
  where decision_relationships.source_entity_type = 'decision'
    and decision_relationships.source_entity_name = 'Horizon CFO Sponsorship Update'
    and decision_relationships.target_entity_type = 'project'
    and decision_relationships.target_entity_name = 'Project Horizon'
    and decision_relationships.relationship_type = 'applies_to'
)
select
  'missing_expected_horizon_sponsorship_context' as issue,
  expected.decision_name,
  expected.sponsor_name,
  expected.project_name
from expected
where not exists (
  select 1
  from actual
  where actual.decision_name = expected.decision_name
    and actual.sponsor_name = expected.sponsor_name
    and actual.project_name = expected.project_name
)

union all

select
  'unexpected_horizon_sponsorship_context' as issue,
  actual.decision_name,
  actual.sponsor_name,
  actual.project_name
from actual
where not exists (
  select 1
  from expected
  where expected.decision_name = actual.decision_name
    and expected.sponsor_name = actual.sponsor_name
    and expected.project_name = actual.project_name
);
