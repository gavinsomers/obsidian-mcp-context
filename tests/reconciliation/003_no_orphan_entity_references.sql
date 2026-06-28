select
  'relationship_source' as reference_type,
  relationships.relationship_id as row_id,
  relationships.source_entity_id as missing_entity_id
from fact_entity_relationships relationships
left join dim_entities entities
  on entities.entity_id = relationships.source_entity_id
where entities.entity_id is null

union all

select
  'relationship_target' as reference_type,
  relationships.relationship_id as row_id,
  relationships.target_entity_id as missing_entity_id
from fact_entity_relationships relationships
left join dim_entities entities
  on entities.entity_id = relationships.target_entity_id
where entities.entity_id is null

union all

select
  'entity_state' as reference_type,
  states.state_id as row_id,
  states.entity_id as missing_entity_id
from fact_entity_states states
left join dim_entities entities
  on entities.entity_id = states.entity_id
where entities.entity_id is null

union all

select
  'entity_event' as reference_type,
  events.event_id as row_id,
  events.entity_id as missing_entity_id
from fact_entity_events events
left join dim_entities entities
  on entities.entity_id = events.entity_id
where entities.entity_id is null

union all

select
  'entity_context' as reference_type,
  context.entity_context_id as row_id,
  context.entity_id as missing_entity_id
from mart_entity_context context
left join dim_entities entities
  on entities.entity_id = context.entity_id
where entities.entity_id is null;
