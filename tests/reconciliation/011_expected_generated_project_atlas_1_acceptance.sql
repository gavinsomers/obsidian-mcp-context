with expected_decisions(title, decision_status, source_path, project_name) as (
  values
    (
      'Project Atlas 1 Security Review Decision 1',
      'superseded',
      'Decisions/Project Atlas 1 Security Review Decision 1.md',
      'Project Atlas 1'
    )
),

actual_decisions as (
  select
    title,
    decision_status,
    source_path,
    projects
  from fact_decisions
  where position(
      ',project atlas 1,'
      in ',' || lower(replace(coalesce(projects, ''), ', ', ',')) || ','
    ) > 0
),

expected_risks(title, risk_status, source_path, project_name) as (
  values
    (
      'Project Atlas 1 Adoption Workflow Risk 1',
      'open',
      'Risks/Project Atlas 1 Adoption Workflow Risk 1.md',
      'Project Atlas 1'
    )
),

actual_risks as (
  select
    title,
    risk_status,
    source_path,
    projects
  from fact_risks
  where position(
      ',project atlas 1,'
      in ',' || lower(replace(coalesce(projects, ''), ', ', ',')) || ','
    ) > 0
),

expected_open_loops(source_path, line_number, task_text, entity_name) as (
  values
    (
      'Meetings/Project Atlas 1 Warehouse Mapping Sync 1.md',
      23,
      'Send recap for [[Project Atlas 1]] to [[Alex Alvarez]] #follow-up',
      'Project Atlas 1'
    ),
    (
      'Decisions/Project Atlas 1 Security Review Decision 1.md',
      27,
      'Review whether [[Project Atlas 1 Security Review Decision 1]] changes open loops for [[Project Atlas 1]] #follow-up',
      'Project Atlas 1'
    ),
    (
      'Research/Project Atlas 1 Contract Renewal Research 1.md',
      21,
      'Convert findings into decision criteria for [[Project Atlas 1]] #research',
      'Project Atlas 1'
    ),
    (
      'Projects/Project Atlas 1.md',
      23,
      'Reconcile latest state for [[Project Atlas 1]] #ops',
      'Project Atlas 1'
    )
),

actual_open_loops as (
  select
    source_path,
    line_number,
    task_text,
    entity_name
  from mart_entity_open_loops
  where entity_type = 'project'
    and entity_name = 'Project Atlas 1'
),

expected_context(source_path, event_type, title, summary_contains, entity_name) as (
  values
    (
      'Decisions/Project Atlas 1 Security Review Decision 1.md',
      'block',
      'Project Atlas 1 Security Review Decision 1 > Decision',
      'Proceed with security review for [[Project Atlas 1]].',
      'Project Atlas 1'
    ),
    (
      'Risks/Project Atlas 1 Adoption Workflow Risk 1.md',
      'block',
      'Project Atlas 1 Adoption Workflow Risk 1 > Risk',
      'Adoption Workflow may affect [[Project Atlas 1]]',
      'Project Atlas 1'
    ),
    (
      'Meetings/Project Atlas 1 Warehouse Mapping Sync 1.md',
      'open_loop',
      'Project Atlas 1 Warehouse Mapping Sync 1 > Action Items',
      'Send recap for [[Project Atlas 1]] to [[Alex Alvarez]] #follow-up',
      'Project Atlas 1'
    )
),

actual_context as (
  select
    source_path,
    event_type,
    title,
    summary,
    entity_name
  from mart_entity_context
  where entity_type = 'project'
    and entity_name = 'Project Atlas 1'
),

expected_timeline(source_path, event_date, event_type, summary_contains) as (
  values
    (
      'Projects/Project Atlas 1.md',
      null,
      'block',
      'Project Atlas 1 supports [[Northstar Labs]] through consulting delivery.'
    ),
    (
      'Meetings/Project Atlas 1 Warehouse Mapping Sync 1.md',
      date '2023-05-20',
      'block',
      'Warehouse Mapping reviewed for [[Project Atlas 1]] at [[Northstar Labs]].'
    )
),

actual_timeline as (
  select
    source_path,
    event_date,
    event_type,
    summary
  from mart_timeline
  where source_path in (
      'Projects/Project Atlas 1.md',
      'Meetings/Project Atlas 1 Warehouse Mapping Sync 1.md'
    )
     or related_entities = 'Project Atlas 1'
     or position(
        ',project atlas 1,'
        in ',' || lower(replace(coalesce(related_entities, ''), ', ', ',')) || ','
      ) > 0
),

variant_leaks as (
  select
    'mart_entity_context_variant_leak' as issue,
    source_path,
    event_type,
    title as observed_value
  from mart_entity_context
  where entity_type = 'project'
    and entity_name = 'Project Atlas 1'
    and (
      lower(coalesce(related_entities, '')) like '%project atlas 16%'
      or lower(coalesce(related_entities, '')) like '%project atlas 31%'
      or lower(coalesce(related_entities, '')) like '%project atlas 46%'
      or lower(coalesce(summary, '')) like '%project atlas 16%'
      or lower(coalesce(summary, '')) like '%project atlas 31%'
      or lower(coalesce(summary, '')) like '%project atlas 46%'
    )

  union all

  select
    'mart_entity_open_loops_variant_leak' as issue,
    source_path,
    'open_loop' as event_type,
    task_text as observed_value
  from mart_entity_open_loops
  where entity_type = 'project'
    and entity_name = 'Project Atlas 1'
    and (
      lower(coalesce(related_entities, '')) like '%project atlas 16%'
      or lower(coalesce(related_entities, '')) like '%project atlas 31%'
      or lower(coalesce(related_entities, '')) like '%project atlas 46%'
      or lower(coalesce(task_text, '')) like '%project atlas 16%'
      or lower(coalesce(task_text, '')) like '%project atlas 31%'
      or lower(coalesce(task_text, '')) like '%project atlas 46%'
    )
)

select
  'missing_generated_atlas_1_decision' as issue,
  expected_decisions.source_path,
  expected_decisions.decision_status as expected_value,
  null as observed_value
from expected_decisions
where not exists (
  select 1
  from actual_decisions
  where actual_decisions.title = expected_decisions.title
    and actual_decisions.decision_status = expected_decisions.decision_status
    and actual_decisions.source_path = expected_decisions.source_path
    and position(
      ',' || lower(expected_decisions.project_name) || ','
      in ',' || lower(replace(coalesce(actual_decisions.projects, ''), ', ', ',')) || ','
    ) > 0
)

union all

select
  'unexpected_generated_atlas_1_decision_variant' as issue,
  actual_decisions.source_path,
  'Project Atlas 1 only' as expected_value,
  actual_decisions.title as observed_value
from actual_decisions
where lower(actual_decisions.title) like '%project atlas 16%'
   or lower(actual_decisions.title) like '%project atlas 31%'
   or lower(actual_decisions.title) like '%project atlas 46%'

union all

select
  'missing_generated_atlas_1_risk' as issue,
  expected_risks.source_path,
  expected_risks.risk_status as expected_value,
  null as observed_value
from expected_risks
where not exists (
  select 1
  from actual_risks
  where actual_risks.title = expected_risks.title
    and actual_risks.risk_status = expected_risks.risk_status
    and actual_risks.source_path = expected_risks.source_path
    and position(
      ',' || lower(expected_risks.project_name) || ','
      in ',' || lower(replace(coalesce(actual_risks.projects, ''), ', ', ',')) || ','
    ) > 0
)

union all

select
  'unexpected_generated_atlas_1_risk_variant' as issue,
  actual_risks.source_path,
  'Project Atlas 1 only' as expected_value,
  actual_risks.title as observed_value
from actual_risks
where lower(actual_risks.title) like '%project atlas 16%'
   or lower(actual_risks.title) like '%project atlas 31%'
   or lower(actual_risks.title) like '%project atlas 46%'

union all

select
  'missing_generated_atlas_1_open_loop' as issue,
  expected_open_loops.source_path,
  expected_open_loops.task_text as expected_value,
  null as observed_value
from expected_open_loops
where not exists (
  select 1
  from actual_open_loops
  where actual_open_loops.source_path = expected_open_loops.source_path
    and actual_open_loops.line_number = expected_open_loops.line_number
    and actual_open_loops.task_text = expected_open_loops.task_text
    and actual_open_loops.entity_name = expected_open_loops.entity_name
)

union all

select
  'missing_generated_atlas_1_context' as issue,
  expected_context.source_path,
  expected_context.event_type as expected_value,
  null as observed_value
from expected_context
where not exists (
  select 1
  from actual_context
  where actual_context.source_path = expected_context.source_path
    and actual_context.event_type = expected_context.event_type
    and actual_context.title = expected_context.title
    and actual_context.entity_name = expected_context.entity_name
    and actual_context.summary like '%' || expected_context.summary_contains || '%'
)

union all

select
  'missing_generated_atlas_1_timeline' as issue,
  expected_timeline.source_path,
  expected_timeline.event_type as expected_value,
  null as observed_value
from expected_timeline
where not exists (
  select 1
  from actual_timeline
  where actual_timeline.source_path = expected_timeline.source_path
    and (
      actual_timeline.event_date = expected_timeline.event_date
      or (actual_timeline.event_date is null and expected_timeline.event_date is null)
    )
    and actual_timeline.event_type = expected_timeline.event_type
    and actual_timeline.summary like '%' || expected_timeline.summary_contains || '%'
)

union all

select
  issue,
  source_path,
  event_type as expected_value,
  observed_value
from variant_leaks;
