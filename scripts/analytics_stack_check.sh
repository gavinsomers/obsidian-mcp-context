#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.analytics.yml}"
vault_size="${1:-${ANALYTICS_VAULT_SIZE:-}}"
if [[ -n "${ENV_FILE:-}" ]]; then
  env_file="$ENV_FILE"
elif [[ -f ".env.analytics" ]]; then
  env_file=".env.analytics"
else
  env_file=".env.analytics.example"
fi

if [[ -n "$vault_size" ]]; then
  case "$vault_size" in
    small|medium|large)
      export VAULT_PATH="./examples/generated-vaults/$vault_size"
      ;;
    synthetic)
      export VAULT_PATH="./examples/synthetic-vault"
      ;;
    *)
      echo "Unknown vault size: $vault_size" >&2
      echo "Use one of: small, medium, large, synthetic" >&2
      exit 2
      ;;
  esac
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
echo "Using vault path: ${VAULT_PATH:-from $env_file}"

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
projects = service.projects(None, limit=5)
people = service.people(None, limit=5)
project = str(projects[0]["name"]) if projects else ""
person = str(people[0]["name"]) if people else ""

checks = {
    "summary_tables": len(summary["tables"]),
    "entities": len(service.list_entities("/vault", limit=5)),
    "entity_types": len(service.entity_types(None, limit=5)),
    "entity_context": len(service.entity_context_generic(None, "project", project, limit=5)) if project else 0,
    "entity_events": len(service.entity_events(None, entity_type="project", entity=project, limit=5)) if project else 0,
    "relationships": len(service.entity_relationships(None, entity=project, limit=5)) if project else 0,
    "states": len(service.entity_states(None, limit=5)),
    "entity_open_loops": len(service.entity_open_loops(None, entity=project, limit=5)) if project else 0,
    "projects": len(projects),
    "people": len(people),
    "companies": len(service.companies(None, limit=5)),
    "project_context": len(service.project_context(None, project, limit=5)) if project else 0,
    "person_context": len(service.person_context(None, person, limit=5)) if person else 0,
    "open_loops": len(service.open_loops(None, limit=5)),
    "decisions": len(service.decisions(None, entity=project, limit=5)) if project else 0,
    "risks": len(service.risks(None, entity=project, limit=5)) if project else 0,
    "timeline": len(service.entity_timeline("/vault", project, limit=5)) if project else 0,
    "agent": len(service.agent_context("/vault", entity=project, event_type="open_loop", limit=5)) if project else 0,
}
print(f"smoke_project: {project}")
print(f"smoke_person: {person}")
for name, count in checks.items():
    print(f"{name}: {count}")
missing = {name: count for name, count in checks.items() if count <= 0}
if missing:
    raise SystemExit(f"Postgres MCP smoke check failed: {missing}")
PY

echo "Postgres analytics stack check passed."
