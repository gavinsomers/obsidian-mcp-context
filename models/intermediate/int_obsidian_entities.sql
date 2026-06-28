with canonical_note_entities as (
  select
    note_type as entity_type,
    title as name,
    source_path,
    note_id as canonical_note_id
  from {{ ref('stg_obsidian_files') }}
  where note_type not in ('daily', 'meeting', 'note', 'research')
),

link_entities as (
  select distinct
    coalesce(notes.note_type, 'unknown') as entity_type,
    links.link_target as name,
    notes.source_path,
    notes.note_id as canonical_note_id
  from {{ ref('stg_obsidian_links') }} links
  left join {{ ref('stg_obsidian_files') }} notes
    on lower(notes.title) = lower(links.link_target)
   and notes.note_type not in ('daily', 'meeting', 'note', 'research')
),

tag_entities as (
  select distinct
    'topic' as entity_type,
    tag as name,
    null as source_path,
    null as canonical_note_id
  from {{ ref('stg_obsidian_tags') }}
),

combined as (
  select * from canonical_note_entities
  union
  select * from link_entities
  union
  select * from tag_entities
),

entity_ids as (
  select
    entity_type || ':' || regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g') as base_entity_id,
    entity_type,
    name,
    source_path,
    canonical_note_id
  from combined
),

collision_counts as (
  select
    base_entity_id,
    count(*) as entity_id_collision_count
  from entity_ids
  group by base_entity_id
)

select
  case
    when collision_counts.entity_id_collision_count > 1 then
      entity_ids.base_entity_id || ':' || substr(md5(entity_ids.entity_type || ':' || entity_ids.name), 1, 8)
    else entity_ids.base_entity_id
  end as entity_id,
  entity_ids.entity_type,
  entity_ids.name,
  entity_ids.source_path,
  entity_ids.canonical_note_id
from entity_ids
join collision_counts
  on collision_counts.base_entity_id = entity_ids.base_entity_id
