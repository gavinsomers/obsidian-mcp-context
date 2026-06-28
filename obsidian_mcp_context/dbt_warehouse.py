from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import duckdb


DEFAULT_DUCKDB_PATH = Path("/warehouse/obsidian.duckdb")
MAX_LIMIT = 500
REQUIRED_MARTS = {
    "dim_notes",
    "dim_entities",
    "dim_entity_types",
    "fact_blocks",
    "fact_tasks",
    "fact_links",
    "fact_tags",
    "fact_mentions",
    "fact_entity_relationships",
    "fact_entity_states",
    "fact_entity_events",
    "dim_people",
    "dim_companies",
    "dim_projects",
    "fact_decisions",
    "fact_risks",
    "mart_open_loops",
    "mart_entity_open_loops",
    "mart_entity_context",
    "mart_person_context",
    "mart_project_context",
}


def resolve_duckdb_path(value: str | Path | None = None) -> Path | None:
    if value:
        path = Path(value).expanduser()
        return path if path.exists() else None
    return DEFAULT_DUCKDB_PATH if DEFAULT_DUCKDB_PATH.exists() else None


@contextmanager
def connect(duckdb_path: str | Path) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        yield connection
    finally:
        connection.close()


def is_available(duckdb_path: str | Path | None) -> bool:
    path = resolve_duckdb_path(duckdb_path)
    if path is None:
        return False
    try:
        with connect(path) as connection:
            rows = _fetchall_dict(
                connection.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'main'
                    """
                )
            )
            tables = {row["table_name"] for row in rows}
    except (duckdb.Error, OSError):
        return False
    return REQUIRED_MARTS.issubset(tables)


def _bounded_limit(limit: int, maximum: int = MAX_LIMIT) -> int:
    return max(1, min(limit, maximum))


def _normalize(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{key: _normalize(value) for key, value in row.items()} for row in rows]


def _fetchall_dict(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    columns = [column[0] for column in cursor.description or []]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _fetchone_dict(cursor: duckdb.DuckDBPyConnection) -> dict[str, object]:
    columns = [column[0] for column in cursor.description or []]
    row = cursor.fetchone()
    if row is None:
        return {}
    return dict(zip(columns, row, strict=True))


def _csv_member_filter(column: str) -> str:
    return f"""
    (
      ',' || lower(replace(coalesce({column}, ''), ', ', ',')) || ','
    ) like (
      '%,' || lower(?) || ',%'
    )
    """


def summary(duckdb_path: str | Path) -> dict[str, object]:
    tables = [
        "dim_notes",
        "dim_entities",
        "dim_entity_types",
        "fact_blocks",
        "fact_tasks",
        "fact_links",
        "fact_tags",
        "fact_mentions",
        "fact_entity_relationships",
        "fact_entity_states",
        "fact_entity_events",
        "fact_decisions",
        "fact_risks",
        "mart_timeline",
        "mart_open_loops",
        "mart_entity_open_loops",
        "mart_entity_context",
        "mart_person_context",
        "mart_project_context",
    ]
    with connect(duckdb_path) as connection:
        counts = {
            table: _fetchone_dict(
                connection.execute(f"select count(*) as count from {table}")
            )["count"]
            for table in tables
        }
        entity_types = _fetchall_dict(
            connection.execute(
                """
                select entity_type, count(*) as count
                from dim_entities
                group by entity_type
                order by entity_type
                """
            )
        )
    return {"tables": counts, "entity_types": _normalize_rows(entity_types)}


def list_entities(
    duckdb_path: str | Path,
    entity_type: str | None = None,
    text: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if entity_type:
        filters.append("entity_type = ?")
        params.append(entity_type)
    if text:
        filters.append("lower(name) like lower(?)")
        params.append(f"%{text}%")
    where = f"where {' and '.join(filters)}" if filters else ""
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                select entity_id, entity_type, name, source_path, canonical_note_id
                from dim_entities
                {where}
                order by entity_type, name
                limit ?
                """,
                (*params, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def list_entity_types(
    duckdb_path: str | Path,
    limit: int = 100,
) -> list[dict[str, object]]:
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                """
                select
                  entity_type,
                  display_name,
                  description,
                  source_strategy,
                  is_stateful,
                  is_actor,
                  is_container
                from dim_entity_types
                order by entity_type
                limit ?
                """,
                (_bounded_limit(limit),),
            )
        )
    return _normalize_rows(rows)


def get_entity(
    duckdb_path: str | Path,
    entity_type: str,
    name: str,
) -> dict[str, object]:
    with connect(duckdb_path) as connection:
        row = _fetchone_dict(
            connection.execute(
                """
                select entity_id, entity_type, name, source_path, canonical_note_id
                from dim_entities
                where entity_type = ?
                  and lower(name) = lower(?)
                """,
                (entity_type, name),
            )
        )
    return {key: _normalize(value) for key, value in row.items()}


def list_projects(
    duckdb_path: str | Path,
    limit: int = 100,
) -> list[dict[str, object]]:
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                """
                select
                  project_id as entity_id,
                  'project' as entity_type,
                  name
                from dim_projects
                order by name
                limit ?
                """,
                (_bounded_limit(limit),),
            )
        )
    return _normalize_rows(rows)


def list_people(
    duckdb_path: str | Path,
    limit: int = 100,
) -> list[dict[str, object]]:
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                """
                select
                  person_id as entity_id,
                  'person' as entity_type,
                  name
                from dim_people
                order by name
                limit ?
                """,
                (_bounded_limit(limit),),
            )
        )
    return _normalize_rows(rows)


def list_companies(
    duckdb_path: str | Path,
    limit: int = 100,
) -> list[dict[str, object]]:
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                """
                select
                  company_id as entity_id,
                  'company' as entity_type,
                  name
                from dim_companies
                order by name
                limit ?
                """,
                (_bounded_limit(limit),),
            )
        )
    return _normalize_rows(rows)


def entity_context(
    duckdb_path: str | Path,
    entity_type: str,
    entity: str,
    limit: int = 50,
) -> list[dict[str, object]]:
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                """
                select
                  entity_context_id as row_id,
                  entity_id,
                  entity_type,
                  entity_name,
                  event_id,
                  event_date,
                  event_type,
                  source_path,
                  start_line,
                  title,
                  summary,
                  related_entities,
                  rank_score
                from mart_entity_context
                where entity_type = ?
                  and lower(entity_name) = lower(?)
                order by coalesce(event_date, date '9999-12-31'), source_path, start_line, row_id
                limit ?
                """,
                (entity_type, entity, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def list_entity_events(
    duckdb_path: str | Path,
    entity_type: str | None = None,
    entity: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if entity_type:
        filters.append("entity_type = ?")
        params.append(entity_type)
    if entity:
        filters.append("lower(entity_name) = lower(?)")
        params.append(entity)
    if event_type:
        filters.append("event_type = ?")
        params.append(event_type)
    where = f"where {' and '.join(filters)}" if filters else ""
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                select
                  event_id as row_id,
                  entity_id,
                  entity_type,
                  entity_name,
                  event_type,
                  event_date,
                  source_path,
                  start_line,
                  title,
                  summary,
                  related_entities
                from fact_entity_events
                {where}
                order by coalesce(event_date, date '9999-12-31'), source_path, start_line, row_id
                limit ?
                """,
                (*params, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def list_entity_relationships(
    duckdb_path: str | Path,
    entity_type: str | None = None,
    entity: str | None = None,
    relationship_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if entity_type:
        filters.append("(source_entity_type = ? or target_entity_type = ?)")
        params.extend([entity_type, entity_type])
    if entity:
        filters.append("(lower(source_entity_name) = lower(?) or lower(target_entity_name) = lower(?))")
        params.extend([entity, entity])
    if relationship_type:
        filters.append("relationship_type = ?")
        params.append(relationship_type)
    where = f"where {' and '.join(filters)}" if filters else ""
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                select
                  relationship_id as row_id,
                  source_entity_id,
                  source_entity_type,
                  source_entity_name,
                  target_entity_id,
                  target_entity_type,
                  target_entity_name,
                  relationship_type,
                  source_path,
                  line_number,
                  confidence,
                  evidence_text
                from fact_entity_relationships
                {where}
                order by source_entity_name, relationship_type, target_entity_name, source_path, line_number
                limit ?
                """,
                (*params, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def list_entity_states(
    duckdb_path: str | Path,
    entity_type: str | None = None,
    entity: str | None = None,
    state_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if entity_type:
        filters.append("entity_type = ?")
        params.append(entity_type)
    if entity:
        filters.append("lower(entity_name) = lower(?)")
        params.append(entity)
    if state_type:
        filters.append("state_type = ?")
        params.append(state_type)
    if status:
        filters.append("state_value = ?")
        params.append(status)
    where = f"where {' and '.join(filters)}" if filters else ""
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                select
                  state_id as row_id,
                  entity_id,
                  entity_type,
                  entity_name,
                  state_type,
                  state_value,
                  state_date,
                  severity,
                  owner_entity_id,
                  owner_entity_name,
                  source_path,
                  title,
                  summary,
                  related_entities
                from fact_entity_states
                {where}
                order by coalesce(state_date, date '9999-12-31'), entity_type, entity_name
                limit ?
                """,
                (*params, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def list_entity_open_loops(
    duckdb_path: str | Path,
    entity_type: str | None = None,
    entity: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if entity_type:
        filters.append("entity_type = ?")
        params.append(entity_type)
    if entity:
        filters.append("lower(entity_name) = lower(?)")
        params.append(entity)
    where = f"where {' and '.join(filters)}" if filters else ""
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                select
                  entity_open_loop_id as row_id,
                  entity_id,
                  entity_type,
                  entity_name,
                  open_loop_id,
                  task_id,
                  source_date as event_date,
                  source_path,
                  line_number as start_line,
                  coalesce(heading_path, source_title) as title,
                  task_text as summary,
                  related_entities,
                  owner_entity_id,
                  owner_entity_name
                from mart_entity_open_loops
                {where}
                order by coalesce(source_date, date '9999-12-31'), source_path, line_number, row_id
                limit ?
                """,
                (*params, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def project_context(
    duckdb_path: str | Path,
    project: str,
    limit: int = 50,
) -> list[dict[str, object]]:
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                with context_rows as (
                  select
                    'context:' || project_context_id as row_id,
                    event_date,
                    event_type,
                    source_path,
                    start_line,
                    title,
                    summary,
                    related_entities
                  from mart_project_context
                  where lower(project_name) = lower(?)
                ),
                decision_rows as (
                  select
                    'decision:' || decision_id as row_id,
                    decision_date as event_date,
                    'decision_' || decision_status as event_type,
                    source_path,
                    null as start_line,
                    title,
                    summary,
                    projects as related_entities
                  from fact_decisions
                  where {_csv_member_filter('projects')}
                ),
                risk_rows as (
                  select
                    'risk:' || risk_id as row_id,
                    risk_date as event_date,
                    'risk_' || risk_status as event_type,
                    source_path,
                    null as start_line,
                    title,
                    summary,
                    projects as related_entities
                  from fact_risks
                  where {_csv_member_filter('projects')}
                ),
                open_loop_rows as (
                  select
                    'open_loop:' || open_loop_id as row_id,
                    source_date as event_date,
                    'open_loop' as event_type,
                    source_path,
                    line_number as start_line,
                    coalesce(heading_path, source_title) as title,
                    task_text as summary,
                    related_entities
                  from mart_open_loops
                  where {_csv_member_filter('projects')}
                )
                select distinct *
                from (
                  select * from context_rows
                  union all
                  select * from decision_rows
                  union all
                  select * from risk_rows
                  union all
                  select * from open_loop_rows
                )
                order by coalesce(event_date, date '9999-12-31'), source_path, start_line
                limit ?
                """,
                (project, project, project, project, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def person_context(
    duckdb_path: str | Path,
    person: str,
    limit: int = 50,
) -> list[dict[str, object]]:
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                with context_rows as (
                  select
                    'context:' || person_context_id as row_id,
                    event_date,
                    event_type,
                    source_path,
                    start_line,
                    title,
                    summary,
                    related_entities
                  from mart_person_context
                  where lower(person_name) = lower(?)
                ),
                decision_rows as (
                  select
                    'decision:' || decision_id as row_id,
                    decision_date as event_date,
                    'decision_' || decision_status as event_type,
                    source_path,
                    null as start_line,
                    title,
                    summary,
                    people as related_entities
                  from fact_decisions
                  where {_csv_member_filter('people')}
                ),
                risk_rows as (
                  select
                    'risk:' || risk_id as row_id,
                    risk_date as event_date,
                    'risk_' || risk_status as event_type,
                    source_path,
                    null as start_line,
                    title,
                    summary,
                    people as related_entities
                  from fact_risks
                  where {_csv_member_filter('people')}
                ),
                open_loop_rows as (
                  select
                    'open_loop:' || open_loop_id as row_id,
                    source_date as event_date,
                    'open_loop' as event_type,
                    source_path,
                    line_number as start_line,
                    coalesce(heading_path, source_title) as title,
                    task_text as summary,
                    related_entities
                  from mart_open_loops
                  where {_csv_member_filter('people')}
                )
                select distinct *
                from (
                  select * from context_rows
                  union all
                  select * from decision_rows
                  union all
                  select * from risk_rows
                  union all
                  select * from open_loop_rows
                )
                order by coalesce(event_date, date '9999-12-31'), source_path, start_line
                limit ?
                """,
                (person, person, person, person, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def list_open_loops(
    duckdb_path: str | Path,
    entity: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if entity:
        filters.append(_csv_member_filter("related_entities"))
        params.append(entity)
    where = f"where {' and '.join(filters)}" if filters else ""
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                select
                  open_loop_id as row_id,
                  source_date as event_date,
                  'open_loop' as event_type,
                  source_path,
                  line_number as start_line,
                  coalesce(heading_path, source_title) as title,
                  task_text as summary,
                  related_entities
                from mart_open_loops
                {where}
                order by coalesce(source_date, date '9999-12-31'), source_path, line_number
                limit ?
                """,
                (*params, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)


def list_decisions(
    duckdb_path: str | Path,
    entity: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    return _list_state_facts(
        duckdb_path,
        table="fact_decisions",
        id_column="decision_id",
        date_column="decision_date",
        status_column="decision_status",
        event_prefix="decision",
        entity=entity,
        status=status,
        limit=limit,
    )


def list_risks(
    duckdb_path: str | Path,
    entity: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    return _list_state_facts(
        duckdb_path,
        table="fact_risks",
        id_column="risk_id",
        date_column="risk_date",
        status_column="risk_status",
        event_prefix="risk",
        entity=entity,
        status=status,
        limit=limit,
    )


def _list_state_facts(
    duckdb_path: str | Path,
    table: str,
    id_column: str,
    date_column: str,
    status_column: str,
    event_prefix: str,
    entity: str | None,
    status: str | None,
    limit: int,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if entity:
        filters.append(
            "("
            + " or ".join(
                [
                    _csv_member_filter("projects"),
                    _csv_member_filter("companies"),
                    _csv_member_filter("people"),
                ]
            )
            + ")"
        )
        params.extend([entity, entity, entity])
    if status:
        filters.append(f"{status_column} = ?")
        params.append(status)
    where = f"where {' and '.join(filters)}" if filters else ""
    with connect(duckdb_path) as connection:
        rows = _fetchall_dict(
            connection.execute(
                f"""
                select
                  {id_column} as row_id,
                  {date_column} as event_date,
                  {status_column} as {event_prefix}_status,
                  '{event_prefix}_' || {status_column} as event_type,
                  source_path,
                  null as start_line,
                  title,
                  summary,
                  trim(concat_ws(', ', projects, companies, people), ', ') as related_entities
                from {table}
                {where}
                order by coalesce({date_column}, date '9999-12-31'), source_path
                limit ?
                """,
                (*params, _bounded_limit(limit)),
            )
        )
    return _normalize_rows(rows)
