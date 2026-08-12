with canonical_note_entities as (
  select
    note_type as entity_type,
    title as name,
    source_path,
    note_id as canonical_note_id
  from {{ ref('stg_obsidian_files') }}
  where note_type not in (
    select note_type
    from {{ source('obsidian', 'base_obsidian_config_non_entity_note_types') }}
  )
),

normalized_links as (
  select
    links.*,
    regexp_replace(
      lower(trim(split_part(split_part(links.link_target, '#', 1), '^', 1))),
      '[.]md$',
      ''
    ) as resolution_key
  from {{ ref('stg_obsidian_links') }} links
),

link_entities as (
  select distinct
    case
      when notes.note_id is null then 'unknown'
      else notes.note_type
    end as entity_type,
    coalesce(notes.title, links.link_target) as name,
    notes.source_path,
    notes.note_id as canonical_note_id
  from normalized_links links
  left join {{ ref('int_obsidian_note_resolution_keys') }} resolution
    on resolution.resolution_key = links.resolution_key
  left join {{ ref('stg_obsidian_files') }} notes
    on notes.note_id = resolution.note_id
  where notes.note_id is null
     or notes.note_type not in (
       select note_type
       from {{ source('obsidian', 'base_obsidian_config_non_entity_note_types') }}
     )
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
