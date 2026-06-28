from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import duckdb

from obsidian_mcp_context.web_ui import ContextHandler


def _write_api_warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            create table dim_notes (note_id text, title text);
            create table dim_entities (
              entity_id text,
              entity_type text,
              name text,
              source_path text,
              canonical_note_id text
            );
            create table fact_blocks (block_id text);
            create table fact_tasks (task_id text);
            create table fact_links (link_id text);
            create table fact_tags (tag_id text);
            create table fact_mentions (mention_id text);
            create table dim_people (person_id text, name text);
            create table dim_companies (company_id text, name text);
            create table dim_projects (project_id text, name text);
            create table mart_timeline (timeline_id text);
            create table mart_project_context (
              project_context_id text,
              project_id text,
              project_name text,
              timeline_id text,
              event_date date,
              event_type text,
              source_path text,
              start_line integer,
              title text,
              summary text,
              related_entities text
            );
            create table mart_person_context (
              person_context_id text,
              person_id text,
              person_name text,
              timeline_id text,
              event_date date,
              event_type text,
              source_path text,
              start_line integer,
              title text,
              summary text,
              related_entities text
            );
            create table fact_decisions (
              decision_id text,
              decision_date date,
              decision_status text,
              source_path text,
              title text,
              summary text,
              projects text,
              companies text,
              people text
            );
            create table fact_risks (
              risk_id text,
              risk_date date,
              risk_status text,
              source_path text,
              title text,
              summary text,
              projects text,
              companies text,
              people text
            );
            create table mart_open_loops (
              open_loop_id text,
              source_date date,
              source_path text,
              line_number integer,
              heading_path text,
              source_title text,
              task_text text,
              related_entities text,
              people text,
              companies text,
              projects text,
              risks text
            );
            insert into dim_entities values
              ('project:atlas', 'project', 'Project Atlas', 'Projects/Atlas.md', 'note:atlas'),
              ('person:morgan', 'person', 'Morgan Lee', 'People/Morgan Lee.md', 'note:morgan');
            insert into dim_projects values ('project:atlas', 'Project Atlas');
            insert into dim_people values ('person:morgan', 'Morgan Lee');
            insert into dim_companies values ('company:northstar', 'Northstar Labs');
            insert into mart_project_context values (
              'pc1', 'project:atlas', 'Project Atlas', 'tl1', date '2026-05-18',
              'block', 'Daily/2026-05-18.md', 10, 'Daily > Notes',
              'Reviewed Project Atlas.', 'Project Atlas, Morgan Lee'
            );
            insert into mart_person_context values (
              'person-context:1', 'person:morgan', 'Morgan Lee', 'tl1',
              date '2026-05-18', 'block', 'Daily/2026-05-18.md', 10,
              'Daily > Notes', 'Morgan reviewed Project Atlas.', 'Project Atlas, Morgan Lee'
            );
            insert into fact_decisions values (
              'decision:1', date '2026-05-19', 'active', 'Decisions/Atlas Scope.md',
              'Atlas Scope', 'Proceed with Project Atlas.', 'Project Atlas',
              'Northstar Labs', 'Morgan Lee'
            );
            insert into fact_risks values (
              'risk:1', date '2026-05-20', 'open', 'Risks/Atlas Risk.md',
              'Atlas Risk', 'Blocked access for Project Atlas.', 'Project Atlas',
              'Northstar Labs', 'Morgan Lee'
            );
            insert into mart_open_loops values (
              'task:1', date '2026-05-21', 'Daily/2026-05-21.md', 7,
              'Daily > Tasks', '2026-05-21', 'Follow up on Project Atlas.',
              'Project Atlas, Morgan Lee', 'Morgan Lee', 'Northstar Labs',
              'Project Atlas', ''
            );
            """
        )
    finally:
        connection.close()


def _get_json(handler: type[ContextHandler], path: str) -> dict[str, object]:
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_formal_project_and_person_api_endpoints(tmp_path: Path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    duckdb_path = tmp_path / "warehouse.duckdb"
    _write_api_warehouse(duckdb_path)
    handler = type(
        "TestContextHandler",
        (ContextHandler,),
        {"vault_path": vault_path, "duckdb_path": duckdb_path},
    )

    projects = _get_json(handler, "/api/projects")
    project_context = _get_json(handler, "/api/projects/Project%20Atlas/context")
    project_risks = _get_json(handler, "/api/projects/Project%20Atlas/risks?status=open")
    people = _get_json(handler, "/api/people")
    person_loops = _get_json(handler, "/api/people/Morgan%20Lee/open-loops")

    assert projects["result"][0]["name"] == "Project Atlas"
    assert project_context["result"][0]["summary"] == "Reviewed Project Atlas."
    assert project_risks["result"][0]["event_type"] == "risk_open"
    assert project_risks["result"][0]["risk_status"] == "open"
    assert people["result"][0]["name"] == "Morgan Lee"
    assert person_loops["result"][0]["event_type"] == "open_loop"


def test_formal_api_reports_missing_dbt_warehouse(tmp_path: Path):
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    handler = type(
        "TestContextHandler",
        (ContextHandler,),
        {"vault_path": vault_path, "duckdb_path": None},
    )

    response = _get_json(handler, "/api/projects")

    assert response == {"error": "dbt warehouse is not available"}
