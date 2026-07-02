with note_entity_mentions as (
  select
    'relationship:note:' || source_entities.entity_id || ':' || mentions.mention_id as relationship_id,
    source_entities.entity_id as source_entity_id,
    source_entities.entity_type as source_entity_type,
    source_entities.name as source_entity_name,
    mentions.target_entity_id,
    mentions.target_entity_type,
    mentions.target_name as target_entity_name,
    case
      when source_entities.entity_type = 'risk' and mentions.target_entity_type = 'project' then 'affects'
      when source_entities.entity_type = 'decision' and mentions.target_entity_type = 'project' then 'applies_to'
      when source_entities.entity_type = 'project' and mentions.target_entity_type = 'company' then 'for_company'
      when source_entities.entity_type = 'person' and mentions.target_entity_type = 'project' then 'associated_with'
      else 'mentions'
    end as relationship_type,
    mentions.note_id,
    mentions.block_id,
    mentions.source_path,
    mentions.line_number,
    1.0 as confidence,
    mentions.mention_context as evidence_text
  from {{ ref('fact_mentions') }} mentions
  join {{ ref('dim_entities') }} source_entities
    on source_entities.canonical_note_id = mentions.note_id
  where mentions.target_entity_id is not null
    and mentions.target_entity_id != source_entities.entity_id
),

co_mentions as (
  select
    'relationship:co_mention:' || left_mentions.mention_id || ':' || right_mentions.mention_id as relationship_id,
    left_mentions.target_entity_id as source_entity_id,
    left_mentions.target_entity_type as source_entity_type,
    left_mentions.target_name as source_entity_name,
    right_mentions.target_entity_id,
    right_mentions.target_entity_type,
    right_mentions.target_name as target_entity_name,
    'co_mentioned_with' as relationship_type,
    left_mentions.note_id,
    left_mentions.block_id,
    left_mentions.source_path,
    left_mentions.line_number,
    0.7 as confidence,
    left_mentions.mention_context as evidence_text
  from {{ ref('fact_mentions') }} left_mentions
  join {{ ref('fact_mentions') }} right_mentions
    on right_mentions.block_id = left_mentions.block_id
   and right_mentions.target_entity_id != left_mentions.target_entity_id
  where left_mentions.target_entity_id is not null
    and right_mentions.target_entity_id is not null
)

select * from note_entity_mentions
union all
select * from co_mentions
