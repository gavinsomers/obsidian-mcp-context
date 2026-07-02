select
  profile_loaded,
  config_loaded,
  profile_ref,
  config_ref,
  include_globs,
  exclude_globs,
  source_extensions,
  folder_note_types,
  non_entity_note_types,
  note_type_counts,
  source_file_count,
  profile_fingerprint
from {{ source('obsidian', 'base_obsidian_ingest_profile') }}
