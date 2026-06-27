with link_entities as (
  select
    links.block_id,
    entities.name
  from {{ ref('int_obsidian_link_resolution') }} links
  join {{ ref('int_obsidian_entities') }} entities
    on entities.entity_id = links.target_entity_id
),

tag_entities as (
  select
    block_id,
    '#' || tag as name
  from {{ ref('stg_obsidian_tags') }}
)

select
  block_id,
  string_agg(distinct name, ', ' order by name) as related_entities
from (
  select * from link_entities
  union all
  select * from tag_entities
)
group by block_id
