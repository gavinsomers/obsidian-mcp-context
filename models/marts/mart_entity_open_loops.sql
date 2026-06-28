{{ config(unique_key='entity_open_loop_id') }}

with open_loop_mentions as (
  select distinct
    open_loops.open_loop_id,
    mentions.target_entity_id as entity_id,
    mentions.target_entity_type as entity_type,
    mentions.target_name as entity_name
  from {{ ref('mart_open_loops') }} open_loops
  join {{ ref('fact_mentions') }} mentions
    on mentions.block_id = open_loops.block_id
  where mentions.target_entity_id is not null
),

open_loop_rows as (
  select
    'entity_open_loop:' || open_loops.open_loop_id || ':' || open_loop_mentions.entity_id as entity_open_loop_id,
    open_loop_mentions.entity_id,
    open_loop_mentions.entity_type,
    open_loop_mentions.entity_name,
    open_loops.open_loop_id,
    open_loops.task_id,
    open_loops.note_id,
    open_loops.source_note_type,
    open_loops.source_title,
    open_loops.source_path,
    open_loops.source_date,
    open_loops.block_id,
    open_loops.line_number,
    open_loops.heading,
    open_loops.heading_path,
    open_loops.task_text,
    open_loops.related_entities,
    nullif(split_part(open_loops.people, ', ', 1), '') as owner_entity_name
  from {{ ref('mart_open_loops') }} open_loops
  join open_loop_mentions
    on open_loop_mentions.open_loop_id = open_loops.open_loop_id
)

select
  open_loop_rows.entity_open_loop_id,
  open_loop_rows.entity_id,
  open_loop_rows.entity_type,
  open_loop_rows.entity_name,
  open_loop_rows.open_loop_id,
  open_loop_rows.task_id,
  open_loop_rows.note_id,
  open_loop_rows.source_note_type,
  open_loop_rows.source_title,
  open_loop_rows.source_path,
  open_loop_rows.source_date,
  open_loop_rows.block_id,
  open_loop_rows.line_number,
  open_loop_rows.heading,
  open_loop_rows.heading_path,
  open_loop_rows.task_text,
  open_loop_rows.related_entities,
  owners.entity_id as owner_entity_id,
  open_loop_rows.owner_entity_name
from open_loop_rows
left join {{ ref('dim_entities') }} owners
  on owners.entity_type = 'person'
 and lower(owners.name) = lower(open_loop_rows.owner_entity_name)
