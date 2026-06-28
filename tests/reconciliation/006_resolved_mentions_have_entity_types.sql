select
  mention_id,
  target_entity_id,
  target_entity_type,
  target_name
from fact_mentions
where target_entity_id is not null
  and target_entity_id not like 'unknown:%'
  and (
    target_entity_type is null
    or target_entity_type = 'unknown'
    or target_name is null
    or trim(target_name) = ''
  );
