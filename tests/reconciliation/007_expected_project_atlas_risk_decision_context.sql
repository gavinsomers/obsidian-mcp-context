with expected(kind, name) as (
  values
    ('decision', 'Atlas Handoff Owner Assignment'),
    ('decision', 'Renewal Prep Scope'),
    ('decision', 'Revised Security Addendum Scope'),
    ('risk', 'Finance Approval Drift'),
    ('risk', 'Pilot Handoff Ownership'),
    ('risk', 'SecOps Access Blocker')
),
actual as (
  select distinct
    'decision' as kind,
    source_entity_name as name
  from fact_entity_relationships
  where source_entity_type = 'decision'
    and target_entity_type = 'project'
    and target_entity_name = 'Project Atlas'
    and relationship_type = 'applies_to'

  union all

  select distinct
    'risk' as kind,
    source_entity_name as name
  from fact_entity_relationships
  where source_entity_type = 'risk'
    and target_entity_type = 'project'
    and target_entity_name = 'Project Atlas'
    and relationship_type = 'affects'
)
select 'missing_expected_atlas_context' as issue, expected.kind, expected.name
from expected
where not exists (
  select 1
  from actual
  where actual.kind = expected.kind
    and actual.name = expected.name
)

union all

select 'unexpected_atlas_context' as issue, actual.kind, actual.name
from actual
where not exists (
  select 1
  from expected
  where expected.kind = actual.kind
    and expected.name = actual.name
);
