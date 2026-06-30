#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.analytics.yml}"
target_vault="${REPLAY_TARGET_VAULT:-./var/replay-vault}"
interval_seconds="${REPLAY_SCHEDULER_INTERVAL_SECONDS:-60}"

if [[ -n "${ENV_FILE:-}" ]]; then
  env_file="$ENV_FILE"
elif [[ -f ".env.analytics" ]]; then
  env_file=".env.analytics"
else
  env_file=".env.analytics.example"
fi

if [[ -x ".venv/bin/python" ]]; then
  python_bin=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
elif command -v python >/dev/null 2>&1; then
  python_bin="python"
else
  echo "Could not find python. Create .venv or install python3." >&2
  exit 127
fi

export VAULT_PATH="$target_vault"
compose=(docker compose --env-file "$env_file" -f "$compose_file")

mkdir -p "$target_vault"

echo "Using compose file: $compose_file"
echo "Using env file: $env_file"
echo "Using replay target vault: $target_vault"
echo "Using scheduler interval: $interval_seconds seconds"

"${compose[@]}" config >/dev/null
"${compose[@]}" up -d postgres

printf -v target_vault_q "%q" "$target_vault"
printf -v env_file_q "%q" "$env_file"
printf -v compose_file_q "%q" "$compose_file"
ingest_command="VAULT_PATH=$target_vault_q docker compose --env-file $env_file_q -f $compose_file_q run --rm ingest"
dbt_command="VAULT_PATH=$target_vault_q docker compose --env-file $env_file_q -f $compose_file_q run --rm dbt"

"$python_bin" -m obsidian_mcp_context.replay_scheduler \
  --vault "$target_vault" \
  --ingest-command "$ingest_command" \
  --dbt-command "$dbt_command" \
  --interval-seconds "$interval_seconds" \
  "$@"
