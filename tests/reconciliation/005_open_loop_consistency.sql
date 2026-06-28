select
  'checked_task_in_open_loops' as issue,
  open_loops.open_loop_id as row_id
from mart_open_loops open_loops
join fact_tasks tasks
  on tasks.task_id = open_loops.task_id
where tasks.checked

union all

select
  'entity_open_loop_missing_base_open_loop' as issue,
  entity_open_loops.entity_open_loop_id as row_id
from mart_entity_open_loops entity_open_loops
left join mart_open_loops open_loops
  on open_loops.open_loop_id = entity_open_loops.open_loop_id
where open_loops.open_loop_id is null;
