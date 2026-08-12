with normalized_links as (
  select
    links.*,
    regexp_replace(
      lower(trim(split_part(split_part(links.link_target, '#', 1), '^', 1))),
      '[.]md$',
      ''
    ) as resolution_key
  from {{ ref('stg_obsidian_links') }} links
),

ranked_links as (
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
  from normalized_links links
  left join {{ ref('int_obsidian_note_resolution_keys') }} resolution
    on resolution.resolution_key = links.resolution_key
  left join {{ ref('int_obsidian_entities') }} entities
    on entities.canonical_note_id = resolution.note_id
    or (
      resolution.note_id is null
      and lower(entities.name) = lower(links.link_target)
    )
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
