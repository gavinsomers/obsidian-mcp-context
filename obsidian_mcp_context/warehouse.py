from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha1
import json
from pathlib import Path
import re
import sqlite3

from obsidian_mcp_context.domain import (
    NON_ENTITY_NOTE_TYPES,
    frontmatter_value,
    link_resolution_key,
    note_resolution_keys,
    slug,
    source_date,
)
from obsidian_mcp_context.vault import VaultContext


@dataclass(frozen=True)
class Warehouse:
    connection: sqlite3.Connection

    def close(self) -> None:
        self.connection.close()


def _dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, object]:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


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

        create table deterministic_suggested_links (
            suggestion_id text primary key,
            source_link_id text not null references fact_links(link_id),
            source_note_id text not null references dim_notes(note_id),
            candidate_target_note_id text not null references dim_notes(note_id),
            link_target text not null,
            suggestion_type text not null,
            deterministic_score real not null,
            rank integer not null,
            signals_json text not null,
            created_at text not null,
            unique(source_link_id, candidate_target_note_id)
        );

        create table ai_suggested_links (
            ai_suggestion_id text primary key,
            source_link_id text not null references fact_links(link_id),
            source_note_id text not null references dim_notes(note_id),
            suggested_target_note_id text not null references dim_notes(note_id),
            suggestion_type text not null,
            confidence_score real not null,
            rationale text not null,
            provider text not null,
            model text not null,
            prompt_version text not null,
            input_hash text not null,
            reviewed_status text not null,
            created_at text not null,
            unique(source_link_id, suggested_target_note_id, provider, model, prompt_version)
        );

        create index idx_dim_entities_name on dim_entities(name);
        create index idx_dim_entities_type on dim_entities(entity_type);
        create index idx_fact_links_target on fact_links(target_entity_id);
        create index idx_fact_tasks_checked on fact_tasks(checked);
        create index idx_mart_timeline_date on mart_timeline(event_date, source_path);
        create index idx_mart_timeline_entities on mart_timeline(related_entities);
        create index idx_deterministic_suggested_links_source
            on deterministic_suggested_links(source_note_id, rank);
        create index idx_ai_suggested_links_review
            on ai_suggested_links(reviewed_status, created_at);
        """
    )


def _insert_note_dimensions(connection: sqlite3.Connection, context: VaultContext) -> None:
    first_block_text_by_source = {
        block.source_path: block.text for block in reversed(context.blocks)
    }
    for source_file in context.files:
        source_path = source_file.source_path
        first_block_text = first_block_text_by_source.get(source_path)
        note_id = _resolve_note_id(connection, source_path)
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
                source_file.note_type,
                source_file.title,
                source_date(source_path, first_block_text),
                frontmatter_value(first_block_text, "source_created_at"),
                frontmatter_value(first_block_text, "source_observed_at"),
                frontmatter_value(first_block_text, "created_at"),
                frontmatter_value(first_block_text, "updated_at"),
            ),
        )


def _note_id(source_path: str) -> str:
    return f"note:{slug(source_path)}"


def _note_id_with_hash(source_path: str) -> str:
    suffix = sha1(source_path.encode("utf-8")).hexdigest()[:8]
    return f"{_note_id(source_path)}:{suffix}"


def _resolve_note_id(connection: sqlite3.Connection, source_path: str) -> str:
    note_id = _note_id(source_path)
    row = connection.execute(
        "select source_path from dim_notes where note_id = ?",
        (note_id,),
    ).fetchone()
    if row is None or row["source_path"] == source_path:
        return note_id
    return _note_id_with_hash(source_path)


def _entity_id(entity_type: str, name: str) -> str:
    return f"{entity_type}:{slug(name)}"


def _entity_id_with_hash(entity_type: str, name: str) -> str:
    suffix = sha1(f"{entity_type}:{name}".encode("utf-8")).hexdigest()[:8]
    return f"{_entity_id(entity_type, name)}:{suffix}"


def _resolve_entity_id(connection: sqlite3.Connection, entity_type: str, name: str) -> str:
    entity_id = _entity_id(entity_type, name)
    row = connection.execute(
        """
        select entity_type, name
        from dim_entities
        where entity_id = ?
        """,
        (entity_id,),
    ).fetchone()
    if row is None or (row["entity_type"] == entity_type and row["name"] == name):
        return entity_id
    return _entity_id_with_hash(entity_type, name)


def _insert_entity(
    connection: sqlite3.Connection,
    entity_type: str,
    name: str,
    source_path: str | None = None,
    canonical_note_id: str | None = None,
) -> str:
    entity_id = _resolve_entity_id(connection, entity_type, name)
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


def _is_entity_note_type(value: str, non_entity_note_types: tuple[str, ...]) -> bool:
    return value not in set(non_entity_note_types)


def _insert_entities(
    connection: sqlite3.Connection,
    non_entity_note_types: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    notes = connection.execute(
        "select note_id, source_path, note_type, title from dim_notes"
    ).fetchall()
    note_by_key: dict[str, dict[str, object] | None] = {}
    for row in notes:
        for key in note_resolution_keys(str(row["source_path"]), str(row["title"])):
            existing = note_by_key.get(key)
            note_by_key[key] = row if existing is None and key not in note_by_key else None

    for row in notes:
        if _is_entity_note_type(row["note_type"], non_entity_note_types):
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
        note = note_by_key.get(link_resolution_key(str(target)))
        if note and not _is_entity_note_type(note["note_type"], non_entity_note_types):
            continue
        if note:
            continue
        _insert_entity(connection, "unknown", target)

    tags = connection.execute("select distinct tag from pending_tags").fetchall()
    for row in tags:
        _insert_entity(connection, "topic", row["tag"])
    return {key: row for key, row in note_by_key.items() if row is not None}


def _executemany_if_rows(
    connection: sqlite3.Connection,
    query: str,
    rows: list[tuple[object, ...]],
) -> None:
    if rows:
        connection.executemany(query, rows)


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
    _executemany_if_rows(
        connection,
        "insert into pending_links (link_target) values (?)",
        [(link.link_target,) for link in context.links],
    )
    _executemany_if_rows(
        connection,
        "insert into pending_tags (tag) values (?)",
        [(tag.tag,) for tag in context.tags],
    )
    note_by_key = _insert_entities(
        connection,
        context.non_entity_note_types or tuple(sorted(NON_ENTITY_NOTE_TYPES)),
    )

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
        target_note = note_by_key.get(link_resolution_key(link.link_target))
        if target_note and _is_entity_note_type(
            str(target_note["note_type"]),
            context.non_entity_note_types or tuple(sorted(NON_ENTITY_NOTE_TYPES)),
        ):
            entity = connection.execute(
                "select entity_id from dim_entities where canonical_note_id = ?",
                (target_note["note_id"],),
            ).fetchone()
        else:
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


def _normalized_match_text(value: str) -> str:
    return slug(Path(value).stem if value.endswith(".md") else value)


def _source_folder(source_path: str) -> str:
    parts = source_path.split("/", 1)
    return parts[0] if len(parts) > 1 else ""


def _tags_by_note(connection: sqlite3.Connection) -> dict[str, set[str]]:
    rows = connection.execute("select note_id, tag from fact_tags").fetchall()
    tags: dict[str, set[str]] = {}
    for row in rows:
        tags.setdefault(str(row["note_id"]), set()).add(str(row["tag"]).casefold())
    return tags


def _candidate_notes(
    connection: sqlite3.Connection,
    aliases_by_source: dict[str, tuple[str, ...]],
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        select note_id, source_path, title, note_type
        from dim_notes
        order by title, source_path
        """
    ).fetchall()
    candidates = []
    for row in rows:
        aliases = aliases_by_source.get(str(row["source_path"]), ())
        candidates.append(
            {
                **row,
                "title_norm": _normalized_match_text(str(row["title"])),
                "path_norm": _normalized_match_text(str(row["source_path"])),
                "alias_norms": [_normalized_match_text(alias) for alias in aliases],
                "aliases": aliases,
            }
        )
    return candidates


def _candidate_signal(
    *,
    link_target: str,
    source_path: str,
    candidate: dict[str, object],
    source_tags: set[str],
    candidate_tags: set[str],
) -> tuple[str, float, dict[str, object]] | None:
    target_norm = _normalized_match_text(link_target)
    target_stem_norm = _normalized_match_text(Path(link_target).name)
    title_norm = str(candidate["title_norm"])
    path_norm = str(candidate["path_norm"])
    alias_norms = set(candidate["alias_norms"])
    signals: dict[str, object] = {
        "link_target": link_target,
        "candidate_title": candidate["title"],
    }

    if target_norm == path_norm:
        signals["match"] = "exact_path"
        return "exact_path", 1.0, signals
    if target_norm == title_norm or target_stem_norm == title_norm:
        signals["match"] = "exact_basename"
        return "exact_basename", 0.95, signals
    if target_norm in alias_norms or target_stem_norm in alias_norms:
        signals["match"] = "exact_alias"
        signals["aliases"] = list(candidate["aliases"])
        return "exact_alias", 0.9, signals

    similarity = SequenceMatcher(None, target_stem_norm, title_norm).ratio()
    if similarity >= 0.72:
        score = min(0.8, 0.5 + ((similarity - 0.72) / 0.28) * 0.3)
        signals["match"] = "string_similarity"
        signals["similarity"] = round(similarity, 3)
        return "string_similarity", round(score, 3), signals

    shared_tags = sorted(source_tags & candidate_tags)
    if shared_tags:
        score = min(0.4, 0.1 + (0.05 * len(shared_tags)))
        if _source_folder(source_path) == _source_folder(str(candidate["source_path"])):
            score += 0.05
        signals["match"] = "shared_metadata"
        signals["shared_tags"] = shared_tags[:10]
        return "shared_metadata", round(score, 3), signals

    return None


def _insert_deterministic_suggested_links(
    connection: sqlite3.Connection,
    context: VaultContext,
    *,
    top_n: int = 10,
) -> None:
    candidates = _candidate_notes(
        connection,
        {source_file.source_path: source_file.aliases for source_file in context.files},
    )
    tags_by_note = _tags_by_note(connection)
    unresolved_links = connection.execute(
        """
        select
            l.link_id,
            l.note_id as source_note_id,
            l.link_target,
            n.source_path,
            e.canonical_note_id
        from fact_links l
        join dim_notes n on n.note_id = l.note_id
        left join dim_entities e on e.entity_id = l.target_entity_id
        where e.canonical_note_id is null
        order by l.link_id
        """
    ).fetchall()
    created_at = datetime.now(timezone.utc).isoformat()

    for link in unresolved_links:
        source_note_id = str(link["source_note_id"])
        source_tags = tags_by_note.get(source_note_id, set())
        best_by_note: dict[str, tuple[str, float, dict[str, object]]] = {}
        for candidate in candidates:
            candidate_note_id = str(candidate["note_id"])
            if candidate_note_id == source_note_id:
                continue
            signal = _candidate_signal(
                link_target=str(link["link_target"]),
                source_path=str(link["source_path"]),
                candidate=candidate,
                source_tags=source_tags,
                candidate_tags=tags_by_note.get(candidate_note_id, set()),
            )
            if signal is None:
                continue
            existing = best_by_note.get(candidate_note_id)
            if existing is None or signal[1] > existing[1]:
                best_by_note[candidate_note_id] = signal

        ranked = sorted(
            best_by_note.items(),
            key=lambda item: (-item[1][1], str(item[0])),
        )[:top_n]
        for rank, (candidate_note_id, (suggestion_type, score, signals)) in enumerate(
            ranked,
            start=1,
        ):
            suggestion_id = (
                f"suggest:{link['link_id']}:{rank}:"
                f"{sha1(candidate_note_id.encode('utf-8')).hexdigest()[:8]}"
            )
            connection.execute(
                """
                insert into deterministic_suggested_links
                    (
                        suggestion_id,
                        source_link_id,
                        source_note_id,
                        candidate_target_note_id,
                        link_target,
                        suggestion_type,
                        deterministic_score,
                        rank,
                        signals_json,
                        created_at
                    )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion_id,
                    link["link_id"],
                    source_note_id,
                    candidate_note_id,
                    link["link_target"],
                    suggestion_type,
                    score,
                    rank,
                    json.dumps(signals, sort_keys=True),
                    created_at,
                ),
            )


def build_warehouse(context: VaultContext) -> Warehouse:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = _dict_factory
    connection.execute("pragma foreign_keys = on")
    _create_schema(connection)
    _insert_note_dimensions(connection, context)
    _insert_facts(connection, context)
    _insert_deterministic_suggested_links(connection, context)
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
        "deterministic_suggested_links",
        "ai_suggested_links",
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


def list_deterministic_suggested_links(
    warehouse: Warehouse,
    limit: int = 100,
) -> list[dict[str, object]]:
    rows = warehouse.connection.execute(
        """
        select
            s.suggestion_id,
            s.source_link_id,
            source.source_path as source_path,
            links.line_number,
            s.link_target,
            target.note_id as candidate_target_note_id,
            target.source_path as candidate_source_path,
            target.title as candidate_title,
            s.suggestion_type,
            s.deterministic_score,
            s.rank,
            s.signals_json
        from deterministic_suggested_links s
        join dim_notes source on source.note_id = s.source_note_id
        join dim_notes target on target.note_id = s.candidate_target_note_id
        join fact_links links on links.link_id = s.source_link_id
        order by s.source_link_id, s.rank
        limit ?
        """,
        (_bounded_limit(limit),),
    ).fetchall()
    return [
        {
            **row,
            "signals": json.loads(str(row["signals_json"])),
        }
        for row in rows
    ]


def insert_ai_suggested_link(
    warehouse: Warehouse,
    *,
    source_link_id: str,
    source_note_id: str,
    suggested_target_note_id: str,
    suggestion_type: str,
    confidence_score: float,
    rationale: str,
    provider: str,
    model: str,
    prompt_version: str,
    input_hash: str,
    created_at: str,
    reviewed_status: str = "pending",
) -> None:
    suggestion_id = (
        f"ai-suggest:{source_link_id}:"
        f"{sha1(f'{suggested_target_note_id}:{provider}:{model}:{prompt_version}'.encode('utf-8')).hexdigest()[:12]}"
    )
    warehouse.connection.execute(
        """
        insert into ai_suggested_links
            (
                ai_suggestion_id,
                source_link_id,
                source_note_id,
                suggested_target_note_id,
                suggestion_type,
                confidence_score,
                rationale,
                provider,
                model,
                prompt_version,
                input_hash,
                reviewed_status,
                created_at
            )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(source_link_id, suggested_target_note_id, provider, model, prompt_version)
        do update set
            confidence_score = excluded.confidence_score,
            rationale = excluded.rationale,
            input_hash = excluded.input_hash,
            reviewed_status = excluded.reviewed_status,
            created_at = excluded.created_at
        """,
        (
            suggestion_id,
            source_link_id,
            source_note_id,
            suggested_target_note_id,
            suggestion_type,
            confidence_score,
            rationale,
            provider,
            model,
            prompt_version,
            input_hash,
            reviewed_status,
            created_at,
        ),
    )


def list_ai_suggested_links(
    warehouse: Warehouse,
    limit: int = 100,
) -> list[dict[str, object]]:
    return warehouse.connection.execute(
        """
        select
            s.ai_suggestion_id,
            s.source_link_id,
            source.source_path as source_path,
            target.note_id as suggested_target_note_id,
            target.source_path as suggested_source_path,
            target.title as suggested_title,
            s.suggestion_type,
            s.confidence_score,
            s.rationale,
            s.provider,
            s.model,
            s.prompt_version,
            s.input_hash,
            s.reviewed_status,
            s.created_at
        from ai_suggested_links s
        join dim_notes source on source.note_id = s.source_note_id
        join dim_notes target on target.note_id = s.suggested_target_note_id
        order by s.created_at, s.source_link_id
        limit ?
        """,
        (_bounded_limit(limit),),
    ).fetchall()


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


def _related_entity_member_sql(alias: str = "m") -> str:
    return f"""
    (
        ',' || lower(replace({alias}.related_entities, ', ', ',')) || ','
    ) like (
        '%,' || lower(?) || ',%'
    )
    """


def entity_timeline(
    warehouse: Warehouse,
    entity: str,
    text: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    filters = [
        f"""
        (
            {_related_entity_member_sql("m")}
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
    params: list[object] = [entity, entity, entity]
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
            f"""
            (
                {_related_entity_member_sql("m")}
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
        params.extend([entity, entity])
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
