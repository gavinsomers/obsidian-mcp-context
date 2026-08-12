with raw_keys as (
  select note_id, lower(title) as resolution_key
  from {{ ref('stg_obsidian_files') }}

  union all

  select
    note_id,
    regexp_replace(lower(source_path), '[.][^./]+$', '') as resolution_key
  from {{ ref('stg_obsidian_files') }}

  union all

  select
    note_id,
    regexp_replace(
      regexp_replace(lower(source_path), '^.*/', ''),
      '[.][^./]+$',
      ''
    ) as resolution_key
  from {{ ref('stg_obsidian_files') }}
),

unique_keys as (
  select
    resolution_key,
    min(note_id) as note_id
  from raw_keys
  where resolution_key <> ''
  group by resolution_key
  having count(distinct note_id) = 1
)

select resolution_key, note_id
from unique_keys
