select
  'context:' || events.event_id as entity_context_id,
  events.entity_id,
  events.entity_type,
  events.entity_name,
  events.event_id,
  events.event_date,
  events.event_type,
  events.note_id,
  events.block_id,
  events.task_id,
  events.source_path,
  events.start_line,
  events.title,
  events.summary,
  events.related_entities,
  case
    when events.event_type = 'open_loop' then 30
    when events.event_type like 'risk_%' then 25
    when events.event_type like 'decision_%' then 20
    when events.event_type like 'task_%' then 10
    else 0
  end as rank_score
from {{ ref('fact_entity_events') }} events
