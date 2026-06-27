from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import sqlite3

from obsidian_mcp_context.vault import VaultContext


DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
FRONTMATTER_DATE_RE = re.compile(
    r"(?ms)\A\s*---.*?^date:\s*[\"']?(\d{4}-\d{2}-\d{2})[\"']?\s*$.*?^---\s*$"
)
FRONTMATTER_FIELD_RE = re.compile(r"(?ms)\A\s*---(?P<body>.*?)^---\s*$")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")
NOTE_TYPE_BY_FOLDER = {
    "companies": "company",
    "daily": "daily",
    "decisions": "decision",
    "meetings": "meeting",
    "people": "person",
    "projects": "project",
    "research": "research",
    "risks": "risk",
}


@dataclass(frozen=True)
class Warehouse:
    connection: sqlite3.Connection

    def close(self) -> None:
        self.connection.close()


def _dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, object]:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def _slug(value: str) -> str:
    normalized = NON_WORD_RE.sub("-", value.casefold()).strip("-")
    return normalized or "unknown"


def _note_title(source_path: str) -> str:
    return Path(source_path).stem


def _note_type(source_path: str) -> str:
    parts = PurePosixPath(source_path).parts
    if not parts:
        return "note"
    return NOTE_TYPE_BY_FOLDER.get(parts[0].casefold(), "note")


def _source_date(source_path: str, text: str | None = None) -> str | None:
    match = DATE_RE.search(source_path)
    if match:
        return match.group(1)
    if text:
        frontmatter_match = FRONTMATTER_DATE_RE.search(text)
        if frontmatter_match:
            return frontmatter_match.group(1)
        content_text = FRONTMATTER_FIELD_RE.sub("", text, count=1)
        content_match = DATE_RE.search(content_text)
        if content_match:
            return content_match.group(1)
    return None


def _frontmatter_value(text: str | None, field: str) -> str | None:
    if not text:
        return None
    frontmatter_match = FRONTMATTER_FIELD_RE.search(text)
    if not frontmatter_match:
        return None
    field_match = re.search(
        rf"(?m)^{re.escape(field)}:\s*[\"']?([^\"'\n]+)[\"']?\s*$",
        frontmatter_match.group("body"),
    )
    if not field_match:
        return None
    return field_match.group(1).strip()


def _bounded_limit(limit: int, maximum: int = 500) -> int:
    return max(1, min(limit, maximum))


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table dim_notes (
            note_id text primary key,
            source_path text not null unique,
            absolute_path text not null,
            note_type text not null,
            title text not null,
            source_date text,
            source_created_at text,
            source_observed_at text,
            created_at text,
            updated_at text
        );

        create table dim_entities (
            entity_id text primary key,
            entity_type text not null,
            name text not null,
            source_path text,
            canonical_note_id text references dim_notes(note_id),
            unique(entity_type, name)
        );

        create table fact_blocks (
            block_id text primary key,
            note_id text not null references dim_notes(note_id),
            block_hash text not null,
            heading text,
            heading_path text,
            heading_level integer not null,
            start_line integer not null,
            end_line integer not null,
            text text not null
        );

        create table fact_tasks (
            task_id text primary key,
            note_id text not null references dim_notes(note_id),
            block_id text not null references fact_blocks(block_id),
            task_text text not null,
            checked integer not null,
            line_number integer not null,
            heading text,
            heading_path text,
            block_hash text not null
        );

        create table fact_links (
            link_id text primary key,
            note_id text not null references dim_notes(note_id),
            block_id text not null references fact_blocks(block_id),
            target_entity_id text references dim_entities(entity_id),
            link_target text not null,
            link_text text not null,
            line_number integer not null
        );

        create table fact_tags (
            tag_id text primary key,
            note_id text not null references dim_notes(note_id),
            block_id text not null references fact_blocks(block_id),
            tag text not null,
            line_number integer not null
        );

        create table mart_timeline (
            timeline_id text primary key,
            event_date text,
            event_type text not null,
            note_id text not null references dim_notes(note_id),
            block_id text references fact_blocks(block_id),
            task_id text references fact_tasks(task_id),
            source_path text not null,
            start_line integer not null,
            end_line integer not null,
            title text not null,
            summary text not null,
            related_entities text not null
        );

        create index idx_dim_entities_name on dim_entities(name);
        create index idx_dim_entities_type on dim_entities(entity_type);
        create index idx_fact_links_target on fact_links(target_entity_id);
        create index idx_fact_tasks_checked on fact_tasks(checked);
        create index idx_mart_timeline_date on mart_timeline(event_date, source_path);
        create index idx_mart_timeline_entities on mart_timeline(related_entities);
        """
    )


def _insert_note_dimensions(connection: sqlite3.Connection, context: VaultContext) -> None:
    first_block_text_by_source = {
        block.source_path: block.text for block in reversed(context.blocks)
    }
    for source_file in context.files:
        source_path = source_file.source_path
        first_block_text = first_block_text_by_source.get(source_path)
        note_id = f"note:{_slug(source_path)}"
        connection.execute(
            """
            insert into dim_notes
                (
                    note_id,
                    source_path,
                    absolute_path,
                    note_type,
                    title,
                    source_date,
                    source_created_at,
                    source_observed_at,
                    created_at,
                    updated_at
                )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_id,
                source_path,
                str(source_file.absolute_path),
                _note_type(source_path),
                _note_title(source_path),
                _source_date(source_path, first_block_text),
                _frontmatter_value(first_block_text, "source_created_at"),
                _frontmatter_value(first_block_text, "source_observed_at"),
                _frontmatter_value(first_block_text, "created_at"),
                _frontmatter_value(first_block_text, "updated_at"),
            ),
        )


def _entity_id(entity_type: str, name: str) -> str:
    return f"{entity_type}:{_slug(name)}"


def _insert_entity(
    connection: sqlite3.Connection,
    entity_type: str,
    name: str,
    source_path: str | None = None,
    canonical_note_id: str | None = None,
) -> str:
    entity_id = _entity_id(entity_type, name)
    connection.execute(
        """
        insert into dim_entities
            (entity_id, entity_type, name, source_path, canonical_note_id)
        values (?, ?, ?, ?, ?)
        on conflict(entity_type, name) do update set
            source_path = coalesce(dim_entities.source_path, excluded.source_path),
            canonical_note_id = coalesce(dim_entities.canonical_note_id, excluded.canonical_note_id)
        """,
        (entity_id, entity_type, name, source_path, canonical_note_id),
    )
    return entity_id


def _insert_entities(connection: sqlite3.Connection) -> None:
    notes = connection.execute(
        "select note_id, source_path, note_type, title from dim_notes"
    ).fetchall()
    note_by_title = {row["title"].casefold(): row for row in notes}

    for row in notes:
        if row["note_type"] in {"company", "person", "project", "decision", "risk"}:
            _insert_entity(
                connection,
                row["note_type"],
                row["title"],
                source_path=row["source_path"],
                canonical_note_id=row["note_id"],
            )

    link_targets = connection.execute(
        "select distinct link_target from pending_links"
    ).fetchall()
    for row in link_targets:
        target = row["link_target"]
        note = note_by_title.get(target.casefold())
        if note and note["note_type"] in {"company", "person", "project", "decision", "risk"}:
            entity_type = note["note_type"]
            source_path = note["source_path"]
            note_id = note["note_id"]
        else:
            entity_type = "unknown"
            source_path = None
            note_id = None
        _insert_entity(
            connection,
            entity_type,
            target,
            source_path=source_path,
            canonical_note_id=note_id,
        )

    tags = connection.execute("select distinct tag from pending_tags").fetchall()
    for row in tags:
        _insert_entity(connection, "topic", row["tag"])


def _note_id_for_source(connection: sqlite3.Connection, source_path: str) -> str:
    row = connection.execute(
        "select note_id from dim_notes where source_path = ?", (source_path,)
    ).fetchone()
    if not row:
        raise ValueError(f"Missing note dimension for source path: {source_path}")
    return str(row["note_id"])


def _insert_facts(connection: sqlite3.Connection, context: VaultContext) -> None:
    connection.execute(
        "create temporary table pending_links (link_target text not null)"
    )
    connection.execute("create temporary table pending_tags (tag text not null)")
    connection.executemany(
        "insert into pending_links (link_target) values (?)",
        [(link.link_target,) for link in context.links],
    )
    connection.executemany(
        "insert into pending_tags (tag) values (?)",
        [(tag.tag,) for tag in context.tags],
    )
    _insert_entities(connection)

    for block in context.blocks:
        note_id = _note_id_for_source(connection, block.source_path)
        connection.execute(
            """
            insert into fact_blocks
                (block_id, note_id, block_hash, heading, heading_path, heading_level,
                 start_line, end_line, text)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block.block_id,
                note_id,
                block.block_hash,
                block.heading,
                block.heading_path,
                block.heading_level,
                block.start_line,
                block.end_line,
                block.text,
            ),
        )

    for task in context.tasks:
        note_id = _note_id_for_source(connection, task.source_path)
        connection.execute(
            """
            insert into fact_tasks
                (task_id, note_id, block_id, task_text, checked, line_number,
                 heading, heading_path, block_hash)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                note_id,
                task.block_id,
                task.task_text,
                int(task.checked),
                task.line_number,
                task.heading,
                task.heading_path,
                task.block_hash,
            ),
        )

    for index, link in enumerate(context.links, start=1):
        note_id = _note_id_for_source(connection, link.source_path)
        entity = connection.execute(
            """
            select entity_id from dim_entities
            where name = ?
            order by case entity_type when 'unknown' then 1 else 0 end
            limit 1
            """,
            (link.link_target,),
        ).fetchone()
        connection.execute(
            """
            insert into fact_links
                (link_id, note_id, block_id, target_entity_id, link_target,
                 link_text, line_number)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"link:{link.block_id}:{link.line_number}:{index}",
                note_id,
                link.block_id,
                entity["entity_id"] if entity else None,
                link.link_target,
                link.link_text,
                link.line_number,
            ),
        )

    for index, tag in enumerate(context.tags, start=1):
        note_id = _note_id_for_source(connection, tag.source_path)
        connection.execute(
            """
            insert into fact_tags
                (tag_id, note_id, block_id, tag, line_number)
            values (?, ?, ?, ?, ?)
            """,
            (
                f"tag:{tag.block_id}:{tag.line_number}:{index}",
                note_id,
                tag.block_id,
                tag.tag,
                tag.line_number,
            ),
        )


def _related_entities_for_block(connection: sqlite3.Connection, block_id: str) -> str:
    rows = connection.execute(
        """
        select distinct e.name
        from fact_links l
        join dim_entities e on e.entity_id = l.target_entity_id
        where l.block_id = ?
        union
        select distinct '#' || t.tag
        from fact_tags t
        where t.block_id = ?
        order by 1
        """,
        (block_id, block_id),
    ).fetchall()
    return ", ".join(str(row["name"]) for row in rows)


def _insert_timeline_mart(connection: sqlite3.Connection) -> None:
    blocks = connection.execute(
        """
        select b.block_id, b.note_id, b.heading, b.heading_path, b.start_line,
               b.end_line, b.text, n.source_path, n.source_date, n.title
        from fact_blocks b
        join dim_notes n on n.note_id = b.note_id
        where trim(b.text) != ''
        """
    ).fetchall()
    for row in blocks:
        title = row["heading_path"] or row["title"]
        connection.execute(
            """
            insert into mart_timeline
                (timeline_id, event_date, event_type, note_id, block_id, task_id,
                 source_path, start_line, end_line, title, summary, related_entities)
            values (?, ?, ?, ?, ?, null, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"block:{row['block_id']}",
                row["source_date"],
                "block",
                row["note_id"],
                row["block_id"],
                row["source_path"],
                row["start_line"],
                row["end_line"],
                title,
                row["text"],
                _related_entities_for_block(connection, row["block_id"]),
            ),
        )

    tasks = connection.execute(
        """
        select t.task_id, t.note_id, t.block_id, t.task_text, t.checked,
               t.line_number, t.heading_path, n.source_path, n.source_date, n.title
        from fact_tasks t
        join dim_notes n on n.note_id = t.note_id
        """
    ).fetchall()
    for row in tasks:
        connection.execute(
            """
            insert into mart_timeline
                (timeline_id, event_date, event_type, note_id, block_id, task_id,
                 source_path, start_line, end_line, title, summary, related_entities)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"task:{row['task_id']}",
                row["source_date"],
                "task_done" if row["checked"] else "task_open",
                row["note_id"],
                row["block_id"],
                row["task_id"],
                row["source_path"],
                row["line_number"],
                row["line_number"],
                row["heading_path"] or row["title"],
                row["task_text"],
                _related_entities_for_block(connection, row["block_id"]),
            ),
        )


def build_warehouse(context: VaultContext) -> Warehouse:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = _dict_factory
    connection.execute("pragma foreign_keys = on")
    _create_schema(connection)
    _insert_note_dimensions(connection, context)
    _insert_facts(connection, context)
    _insert_timeline_mart(connection)
    return Warehouse(connection=connection)


def warehouse_summary(warehouse: Warehouse) -> dict[str, object]:
    connection = warehouse.connection
    tables = (
        "dim_notes",
        "dim_entities",
        "fact_blocks",
        "fact_tasks",
        "fact_links",
        "fact_tags",
        "mart_timeline",
    )
    counts = {
        table: connection.execute(f"select count(*) as count from {table}").fetchone()[
            "count"
        ]
        for table in tables
    }
    entity_types = connection.execute(
        """
        select entity_type, count(*) as count
        from dim_entities
        group by entity_type
        order by entity_type
        """
    ).fetchall()
    return {"tables": counts, "entity_types": entity_types}


def list_entities(
    warehouse: Warehouse,
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
        filters.append("name like ?")
        params.append(f"%{text}%")
    where = f"where {' and '.join(filters)}" if filters else ""
    return warehouse.connection.execute(
        f"""
        select entity_id, entity_type, name, source_path, canonical_note_id
        from dim_entities
        {where}
        order by entity_type, name
        limit ?
        """,
        (*params, _bounded_limit(limit)),
    ).fetchall()


def entity_timeline(
    warehouse: Warehouse,
    entity: str,
    text: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    filters = [
        """
        (
            lower(m.related_entities) like lower(?)
            or lower(n.title) = lower(?)
            or exists (
                select 1
                from fact_links l
                join dim_entities e on e.entity_id = l.target_entity_id
                where l.block_id = m.block_id
                  and lower(e.name) = lower(?)
            )
        )
        """
    ]
    params: list[object] = [f"%{entity}%", entity, entity]
    if text:
        filters.append("lower(m.summary) like lower(?)")
        params.append(f"%{text}%")

    return warehouse.connection.execute(
        f"""
        select m.timeline_id, m.event_date, m.event_type, m.source_path,
               m.start_line, m.end_line, m.title, m.summary, m.related_entities
        from mart_timeline m
        join dim_notes n on n.note_id = m.note_id
        where {' and '.join(filters)}
        order by coalesce(m.event_date, '9999-12-31'), m.source_path, m.start_line
        limit ?
        """,
        (*params, _bounded_limit(limit)),
    ).fetchall()


def agent_context(
    warehouse: Warehouse,
    text: str | None = None,
    entity: str | None = None,
    event_type: str | None = None,
    limit: int = 25,
) -> list[dict[str, object]]:
    filters: list[str] = []
    params: list[object] = []
    if text:
        filters.append("lower(m.summary) like lower(?)")
        params.append(f"%{text}%")
    if entity:
        filters.append(
            """
            (
                lower(m.related_entities) like lower(?)
                or exists (
                    select 1
                    from fact_links l
                    join dim_entities e on e.entity_id = l.target_entity_id
                    where l.block_id = m.block_id
                      and lower(e.name) = lower(?)
                )
            )
            """
        )
        params.extend([f"%{entity}%", entity])
    if event_type:
        filters.append("m.event_type = ?")
        params.append(event_type)
    where = f"where {' and '.join(filters)}" if filters else ""
    return warehouse.connection.execute(
        f"""
        select m.timeline_id, m.event_date, m.event_type, m.source_path,
               m.start_line, m.end_line, m.title, m.summary, m.related_entities
        from mart_timeline m
        {where}
        order by
            case when m.event_type = 'task_open' then 0 else 1 end,
            coalesce(m.event_date, '9999-12-31'),
            m.source_path,
            m.start_line
        limit ?
        """,
        (*params, _bounded_limit(limit)),
    ).fetchall()
