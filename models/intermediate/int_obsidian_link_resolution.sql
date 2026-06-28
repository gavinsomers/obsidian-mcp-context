with ranked_links as (
  select
    links.source_path,
    links.block_id,
    links.link_target,
    links.link_text,
    links.line_number,
    entities.entity_id as target_entity_id,
    row_number() over (
      partition by
        links.source_path,
        links.block_id,
        links.line_number,
        links.link_target
      order by case when entities.entity_type = 'unknown' then 1 else 0 end
    ) as match_rank
  from {{ ref('stg_obsidian_links') }} links
  left join {{ ref('int_obsidian_entities') }} entities
    on lower(entities.name) = lower(links.link_target)
)

select
  source_path,
  block_id,
  link_target,
  link_text,
  line_number,
  target_entity_id
from ranked_links
where match_rank = 1
