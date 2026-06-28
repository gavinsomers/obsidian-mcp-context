#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.analytics.yml}"
if [[ -n "${ENV_FILE:-}" ]]; then
  env_file="$ENV_FILE"
elif [[ -f ".env.analytics" ]]; then
  env_file=".env.analytics"
else
  env_file=".env.analytics.example"
fi

compose=(docker compose --env-file "$env_file" -f "$compose_file")

cleanup() {
  if [[ "${ANALYTICS_STACK_KEEP_RUNNING:-0}" != "1" ]]; then
    "${compose[@]}" down >/dev/null
  fi
}
trap cleanup EXIT

echo "Using compose file: $compose_file"
echo "Using env file: $env_file"

"${compose[@]}" config >/dev/null
"${compose[@]}" build ingest dbt mcp
"${compose[@]}" up -d postgres
"${compose[@]}" run --rm ingest
"${compose[@]}" run --rm dbt
"${compose[@]}" run --rm dbt-test

"${compose[@]}" run --rm -T mcp python - <<'PY'
from obsidian_mcp_context.services import ContextService

service = ContextService()
summary = service.warehouse_summary("/vault")
checks = {
    "summary_tables": len(summary["tables"]),
    "entities": len(service.list_entities("/vault", limit=5)),
    "entity_types": len(service.entity_types(None, limit=5)),
    "entity_context": len(service.entity_context_generic(None, "project", "Project Atlas", limit=5)),
    "entity_events": len(service.entity_events(None, entity_type="project", entity="Project Atlas", limit=5)),
    "relationships": len(service.entity_relationships(None, entity="Project Atlas", limit=5)),
    "states": len(service.entity_states(None, limit=5)),
    "entity_open_loops": len(service.entity_open_loops(None, entity="Project Atlas", limit=5)),
    "projects": len(service.projects(None, limit=5)),
    "people": len(service.people(None, limit=5)),
    "companies": len(service.companies(None, limit=5)),
    "project_context": len(service.project_context(None, "Project Atlas", limit=5)),
    "person_context": len(service.person_context(None, "Alex Grant", limit=5)),
    "open_loops": len(service.open_loops(None, limit=5)),
    "decisions": len(service.decisions(None, entity="Project Atlas", limit=5)),
    "risks": len(service.risks(None, entity="Project Atlas", limit=5)),
    "timeline": len(service.entity_timeline("/vault", "Project Atlas", limit=5)),
    "agent": len(service.agent_context("/vault", entity="Project Atlas", event_type="open_loop", limit=5)),
}
for name, count in checks.items():
    print(f"{name}: {count}")
missing = {name: count for name, count in checks.items() if count <= 0}
if missing:
    raise SystemExit(f"Postgres MCP smoke check failed: {missing}")
PY

echo "Postgres analytics stack check passed."
