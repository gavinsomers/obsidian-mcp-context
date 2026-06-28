with expected(entity_name, open_loop_count, owner_count) as (
  values
    ('Project Atlas', 29, 4),
    ('Project Horizon', 20, 3),
    ('Project Pipeline', 22, 2)
),
actual as (
  select
    entity_name,
    count(*) as open_loop_count,
    count(distinct owner_entity_name) filter (
      where owner_entity_name is not null
    ) as owner_count
  from mart_entity_open_loops
  where entity_type = 'project'
    and entity_name in ('Project Atlas', 'Project Horizon', 'Project Pipeline')
  group by entity_name
)
select
  'missing_expected_project_open_loop_rollup' as issue,
  expected.entity_name,
  expected.open_loop_count,
  expected.owner_count
from expected
where not exists (
  select 1
  from actual
  where actual.entity_name = expected.entity_name
    and actual.open_loop_count = expected.open_loop_count
    and actual.owner_count = expected.owner_count
)

union all

select
  'unexpected_project_open_loop_rollup' as issue,
  actual.entity_name,
  actual.open_loop_count,
  actual.owner_count
from actual
where not exists (
  select 1
  from expected
  where expected.entity_name = actual.entity_name
    and expected.open_loop_count = actual.open_loop_count
    and expected.owner_count = actual.owner_count
);
