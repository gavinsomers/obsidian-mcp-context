from obsidian_mcp_context.pipeline_reconciliation import (
    reconcile_counts,
    render_markdown,
)


def _matching_counts() -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, int]]:
    parser = {
        "markdown_files": 2,
        "blocks": 5,
        "tasks": 3,
        "links": 4,
        "tags": 6,
        "lines": 20,
    }
    raw = {
        "base_obsidian_files": 2,
        "base_obsidian_blocks": 5,
        "base_obsidian_tasks": 3,
        "base_obsidian_links": 4,
        "base_obsidian_tags": 6,
        "base_obsidian_lines": 20,
    }
    dbt = {
        "stg_obsidian_files": 2,
        "stg_obsidian_blocks": 5,
        "stg_obsidian_tasks": 3,
        "stg_obsidian_links": 4,
        "stg_obsidian_tags": 6,
        "stg_obsidian_lines": 20,
        "stg_obsidian_ingest_profile": 1,
        "dim_notes": 2,
        "fact_blocks": 5,
        "fact_tasks": 3,
        "fact_links": 4,
        "fact_tags": 6,
        "mart_open_loops": 2,
        "mart_entity_context": 2,
        "mart_entity_open_loops": 1,
    }
    service = {
        "warehouse_dim_notes": 2,
        "warehouse_fact_tasks": 3,
        "warehouse_fact_links": 4,
    }
    return parser, raw, dbt, service


def test_reconcile_counts_passes_matching_pipeline_boundaries():
    parser, raw, dbt, service = _matching_counts()

    checks = reconcile_counts(
        parser_counts=parser,
        raw_counts=raw,
        dbt_counts=dbt,
        service_counts=service,
    )

    assert checks
    assert {check["status"] for check in checks} == {"pass"}


def test_reconcile_counts_fails_mismatched_pipeline_boundaries():
    parser, raw, dbt, service = _matching_counts()
    dbt["fact_tasks"] = 2
    service["warehouse_fact_tasks"] = 2

    checks = reconcile_counts(
        parser_counts=parser,
        raw_counts=raw,
        dbt_counts=dbt,
        service_counts=service,
    )

    failed = [check for check in checks if check["status"] == "fail"]
    assert failed == [
        {
            "name": "tasks_raw_to_fact",
            "operator": "equal",
            "left": {
                "section": "raw",
                "key": "base_obsidian_tasks",
                "value": 3,
            },
            "right": {"section": "dbt", "key": "fact_tasks", "value": 2},
            "status": "fail",
        }
    ]


def test_reconcile_counts_allows_modeled_links_to_filter_raw_links():
    parser, raw, dbt, service = _matching_counts()
    dbt["stg_obsidian_links"] = 4
    dbt["fact_links"] = 3

    checks = reconcile_counts(
        parser_counts=parser,
        raw_counts=raw,
        dbt_counts=dbt,
        service_counts=service,
    )

    link_check = next(
        check for check in checks if check["name"] == "links_staging_to_fact_non_expansion"
    )
    assert link_check["status"] == "pass"
    assert link_check["operator"] == "less_than_or_equal"


def test_render_markdown_is_aggregate_only():
    report = {
        "generated_at": "2026-07-03T13:00:00+00:00",
        "vault_name": "snapshot-id",
        "summary": {"status": "pass", "check_count": 1, "failed_count": 0},
        "checks": [
            {
                "name": "notes",
                "left": {"section": "parser", "key": "markdown_files", "value": 2},
                "right": {"section": "raw", "key": "base_obsidian_files", "value": 2},
                "status": "pass",
            }
        ],
    }

    rendered = render_markdown(report)

    assert "snapshot-id" in rendered
    assert "/home/gavman" not in rendered
    assert "secret note text" not in rendered
    assert "sidecar.pdf" not in rendered
