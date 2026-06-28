select 'fact_blocks.note_id' as reference_type, blocks.block_id as row_id
from fact_blocks blocks
left join dim_notes notes
  on notes.note_id = blocks.note_id
where notes.note_id is null

union all

select 'fact_tasks.note_id' as reference_type, tasks.task_id as row_id
from fact_tasks tasks
left join dim_notes notes
  on notes.note_id = tasks.note_id
where notes.note_id is null

union all

select 'fact_tasks.block_id' as reference_type, tasks.task_id as row_id
from fact_tasks tasks
left join fact_blocks blocks
  on blocks.block_id = tasks.block_id
where blocks.block_id is null

union all

select 'fact_links.note_id' as reference_type, links.link_id as row_id
from fact_links links
left join dim_notes notes
  on notes.note_id = links.note_id
where notes.note_id is null

union all

select 'fact_links.block_id' as reference_type, links.link_id as row_id
from fact_links links
left join fact_blocks blocks
  on blocks.block_id = links.block_id
where blocks.block_id is null

union all

select 'fact_mentions.note_id' as reference_type, mentions.mention_id as row_id
from fact_mentions mentions
left join dim_notes notes
  on notes.note_id = mentions.note_id
where notes.note_id is null

union all

select 'fact_mentions.block_id' as reference_type, mentions.mention_id as row_id
from fact_mentions mentions
left join fact_blocks blocks
  on blocks.block_id = mentions.block_id
where blocks.block_id is null

union all

select 'mart_timeline.note_id' as reference_type, timeline.timeline_id as row_id
from mart_timeline timeline
left join dim_notes notes
  on notes.note_id = timeline.note_id
where notes.note_id is null

union all

select 'mart_timeline.block_id' as reference_type, timeline.timeline_id as row_id
from mart_timeline timeline
left join fact_blocks blocks
  on blocks.block_id = timeline.block_id
where timeline.block_id is not null
  and blocks.block_id is null

union all

select 'mart_timeline.task_id' as reference_type, timeline.timeline_id as row_id
from mart_timeline timeline
left join fact_tasks tasks
  on tasks.task_id = timeline.task_id
where timeline.task_id is not null
  and tasks.task_id is null;
