{{ config(unique_key='entity_type') }}

with observed_types as (
  select distinct entity_type
  from {{ ref('dim_entities') }}
),

defined_types as (
  select *
  from (
    values
      ('person', 'Person', 'A human actor mentioned in the vault.', 'note_or_link', true, true, false),
      ('company', 'Company', 'An organization, account, client, or vendor.', 'note_or_link', true, false, true),
      ('project', 'Project', 'A project, initiative, or delivery workstream.', 'note_or_link', true, false, true),
      ('decision', 'Decision', 'A recorded decision note or linked decision entity.', 'note_or_link', true, false, false),
      ('risk', 'Risk', 'A tracked risk note or linked risk entity.', 'note_or_link', true, false, false),
      ('topic', 'Topic', 'A tag-derived topic or theme.', 'tag', false, false, false),
      ('unknown', 'Unknown', 'A linked entity without a typed canonical note.', 'link', false, false, false)
  ) as t(
    entity_type,
    display_name,
    description,
    source_strategy,
    is_stateful,
    is_actor,
    is_container
  )
)

select
  observed_types.entity_type,
  coalesce(defined_types.display_name, replace(observed_types.entity_type, '_', ' ')) as display_name,
  coalesce(defined_types.description, 'Entity type observed in the vault.') as description,
  coalesce(defined_types.source_strategy, 'observed') as source_strategy,
  coalesce(defined_types.is_stateful, false) as is_stateful,
  coalesce(defined_types.is_actor, false) as is_actor,
  coalesce(defined_types.is_container, false) as is_container
from observed_types
left join defined_types
  on defined_types.entity_type = observed_types.entity_type
