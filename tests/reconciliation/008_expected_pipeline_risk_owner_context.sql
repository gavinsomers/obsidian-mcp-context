with expected(risk_name, owner_name, severity) as (
  values
    ('Analyst Enablement Gap', 'David Chen', 'medium'),
    ('Contract Signature Delay', 'David Chen', 'medium'),
    ('Warehouse Mapping Drift', 'David Chen', 'high')
),
actual as (
  select distinct
    entity_name as risk_name,
    owner_entity_name as owner_name,
    severity
  from fact_entity_states
  where entity_type = 'risk'
    and related_entities like '%Project Pipeline%'
)
select
  'missing_expected_pipeline_risk_owner' as issue,
  expected.risk_name,
  expected.owner_name,
  expected.severity
from expected
where not exists (
  select 1
  from actual
  where actual.risk_name = expected.risk_name
    and actual.owner_name = expected.owner_name
    and actual.severity = expected.severity
)

union all

select
  'unexpected_pipeline_risk_owner' as issue,
  actual.risk_name,
  actual.owner_name,
  actual.severity
from actual
where not exists (
  select 1
  from expected
  where expected.risk_name = actual.risk_name
    and expected.owner_name = actual.owner_name
    and expected.severity = actual.severity
);
