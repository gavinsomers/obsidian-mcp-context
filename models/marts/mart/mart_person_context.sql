select
  mentions.mention_id || ':' || timeline.timeline_id as person_context_id,
  mentions.target_entity_id as person_id,
  mentions.target_name as person_name,
  timeline.timeline_id,
  timeline.event_date,
  timeline.event_type,
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
where mentions.target_entity_type = 'person'
