with keys as (
  select 'dim_notes.note_id' as key_name, note_id as key_value, count(*) as row_count
  from dim_notes
  group by note_id
  union all
  select 'dim_entities.entity_id', entity_id, count(*)
  from dim_entities
  group by entity_id
  union all
  select 'fact_blocks.block_id', block_id, count(*)
  from fact_blocks
  group by block_id
  union all
  select 'fact_tasks.task_id', task_id, count(*)
  from fact_tasks
  group by task_id
  union all
  select 'fact_links.link_id', link_id, count(*)
  from fact_links
  group by link_id
  union all
  select 'fact_mentions.mention_id', mention_id, count(*)
  from fact_mentions
  group by mention_id
  union all
  select 'fact_entity_relationships.relationship_id', relationship_id, count(*)
  from fact_entity_relationships
  group by relationship_id
  union all
  select 'fact_entity_events.event_id', event_id, count(*)
  from fact_entity_events
  group by event_id
  union all
  select 'mart_entity_context.entity_context_id', entity_context_id, count(*)
  from mart_entity_context
  group by entity_context_id
)
select key_name, key_value, row_count
from keys
where key_value is null
   or row_count > 1;
