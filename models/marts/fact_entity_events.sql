with mention_events as (
  select
    'event:mention:' || mentions.mention_id || ':' || timeline.timeline_id as event_id,
    mentions.target_entity_id as entity_id,
    mentions.target_entity_type as entity_type,
    mentions.target_name as entity_name,
    timeline.event_type,
    timeline.event_date,
    timeline.note_id,
    timeline.block_id,
    timeline.task_id,
    timeline.source_path,
    timeline.start_line,
    timeline.title,
    timeline.summary,
    timeline.related_entities
  from {{ ref('fact_mentions') }} mentions
  join {{ ref('mart_timeline') }} timeline
    on timeline.block_id = mentions.block_id
  where mentions.target_entity_id is not null
),

state_events as (
  select
    'event:' || states.state_id as event_id,
    states.entity_id,
    states.entity_type,
    states.entity_name,
    states.entity_type || '_' || states.state_value as event_type,
    states.state_date as event_date,
    states.note_id,
    null as block_id,
    null as task_id,
    states.source_path,
    null as start_line,
    states.title,
    states.summary,
    states.related_entities
  from {{ ref('fact_entity_states') }} states
),

open_loop_events as (
  select
    'event:open_loop:' || open_loops.entity_open_loop_id as event_id,
    open_loops.entity_id,
    open_loops.entity_type,
    open_loops.entity_name,
    'open_loop' as event_type,
    open_loops.source_date as event_date,
    open_loops.note_id,
    open_loops.block_id,
    open_loops.task_id,
    open_loops.source_path,
    open_loops.line_number as start_line,
    coalesce(open_loops.heading_path, open_loops.source_title) as title,
    open_loops.task_text as summary,
    open_loops.related_entities
  from {{ ref('mart_entity_open_loops') }} open_loops
)

select * from mention_events
union all
select * from state_events
union all
select * from open_loop_events
