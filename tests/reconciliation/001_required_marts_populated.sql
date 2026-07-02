with mart_counts as (
  select 'dim_notes' as table_name, count(*) as row_count from dim_notes
  union all select 'dim_entities', count(*) from dim_entities
  union all select 'dim_entity_types', count(*) from dim_entity_types
  union all select 'fact_blocks', count(*) from fact_blocks
  union all select 'fact_tasks', count(*) from fact_tasks
  union all select 'fact_links', count(*) from fact_links
  union all select 'fact_tags', count(*) from fact_tags
  union all select 'fact_mentions', count(*) from fact_mentions
  union all select 'fact_entity_relationships', count(*) from fact_entity_relationships
  union all select 'fact_entity_states', count(*) from fact_entity_states
  union all select 'fact_entity_events', count(*) from fact_entity_events
  union all select 'mart_timeline', count(*) from mart_timeline
  union all select 'mart_entity_context', count(*) from mart_entity_context
  union all select 'mart_entity_open_loops', count(*) from mart_entity_open_loops
  union all select 'mart_person_summary', count(*) from mart_person_summary
  union all select 'mart_company_summary', count(*) from mart_company_summary
  union all select 'mart_project_summary', count(*) from mart_project_summary
)
select table_name, row_count
from mart_counts
where row_count = 0;
