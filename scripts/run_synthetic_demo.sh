#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_synthetic_demo.sh [small|medium|large] [options]
  scripts/run_synthetic_demo.sh stop
  scripts/run_synthetic_demo.sh status

Start the isolated generated-vault demo stack:
  Obsidian webtop, Postgres, MCP, Adminer, replay dashboard, Q&A page,
  optional dbt docs, replay loader, and virtual-time ingest/dbt scheduler.

Options:
  --reset                         Reset the isolated replay vault first. Default.
  --no-reset                      Resume the existing isolated replay vault.
  --speed SECONDS                 Virtual seconds per real second. Default: 86400.
  --batch-size COUNT              Replay notes per tick. Default: 25.
  --scheduler-interval SECONDS    Ingest/dbt scheduler cadence. Default: 60.
  --initial-limit COUNT           Seed the first COUNT replay notes before first dbt run.
                                  Default: 3.
  --no-continuous                 Do not start background replay/scheduler loops.
  --no-dbt-docs                   Do not start dbt docs service.
  --help                          Show this help.

Environment:
  ENV_FILE                        Compose env file. Defaults to .env.analytics,
                                  then .env.analytics.example.
  COMPOSE_FILE                    Compose file. Default: docker-compose.analytics.yml.
  REPLAY_TARGET_VAULT             Isolated target. Default: ./var/replay-vault.
  DEMO_ALLOW_CUSTOM_RESET=1       Allow --reset outside ./var.
EOF
}

compose_file="${COMPOSE_FILE:-docker-compose.analytics.yml}"
command="start"
if [[ $# -gt 0 ]]; then
  command="$1"
fi

if [[ "$command" == "--help" || "$command" == "-h" ]]; then
  usage
  exit 0
fi

if [[ -n "${ENV_FILE:-}" ]]; then
  env_file="$ENV_FILE"
elif [[ -f ".env.analytics" ]]; then
  env_file=".env.analytics"
else
  env_file=".env.analytics.example"
fi

target_vault="${REPLAY_TARGET_VAULT:-./var/replay-vault}"
state_dir="var/synthetic-demo"
log_dir="logs/synthetic-demo"
replay_pid_file="$state_dir/replay.pid"
scheduler_pid_file="$state_dir/scheduler.pid"
size="large"
reset=1
continuous=1
start_dbt_docs=1
speed="${REPLAY_DEMO_SPEED:-86400}"
batch_size="${REPLAY_DEMO_BATCH_SIZE:-25}"
scheduler_interval="${REPLAY_SCHEDULER_INTERVAL_SECONDS:-60}"
initial_limit="${REPLAY_DEMO_INITIAL_LIMIT:-3}"

status_for_pid_file() {
  local name="$1"
  local pid_file="$2"
  local pid
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      echo "$name: running pid $pid"
      return
    fi
    rm -f "$pid_file"
  fi
  echo "$name: stopped"
}

if [[ "$command" == "stop" ]]; then
  compose=(docker compose --env-file "$env_file" -f "$compose_file")
  mkdir -p "$state_dir"
  for pid_file in "$replay_pid_file" "$scheduler_pid_file"; do
    if [[ -f "$pid_file" ]]; then
      pid="$(cat "$pid_file")"
      if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
      rm -f "$pid_file"
    fi
  done
  "${compose[@]}" stop vault-obsidian postgres mcp postgres-browser replay-dashboard replay-qa dbt-docs >/dev/null || true
  echo "Synthetic demo stopped."
  exit 0
fi

if [[ "$command" == "status" ]]; then
  compose=(docker compose --env-file "$env_file" -f "$compose_file")
  "${compose[@]}" ps postgres vault-obsidian mcp postgres-browser replay-dashboard replay-qa dbt-docs || true
  status_for_pid_file replay "$replay_pid_file"
  status_for_pid_file scheduler "$scheduler_pid_file"
  exit 0
fi

if [[ "$command" == "start" ]]; then
  if [[ $# -gt 0 ]]; then
    shift
  fi
elif [[ "$command" == --* ]]; then
  command="start"
elif [[ "$command" != "start" ]]; then
  size="$command"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset)
      reset=1
      shift
      ;;
    --no-reset)
      reset=0
      shift
      ;;
    --speed)
      speed="$2"
      shift 2
      ;;
    --batch-size)
      batch_size="$2"
      shift 2
      ;;
    --scheduler-interval)
      scheduler_interval="$2"
      shift 2
      ;;
    --initial-limit)
      initial_limit="$2"
      shift 2
      ;;
    --no-continuous)
      continuous=0
      shift
      ;;
    --no-dbt-docs)
      start_dbt_docs=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$size" in
  small|medium|large)
    source_vault="./examples/generated-vaults/$size"
    ;;
  *)
    echo "Unknown vault size: $size" >&2
    echo "Use one of: small, medium, large" >&2
    exit 2
    ;;
esac

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

compose=(docker compose --env-file "$env_file" -f "$compose_file")

env_value() {
  local key="$1"
  local default="$2"
  local value
  value="$(grep -E "^${key}=" "$env_file" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  printf '%s' "${!key:-${value:-$default}}"
}

stop_background_processes() {
  mkdir -p "$state_dir"
  for pid_file in "$replay_pid_file" "$scheduler_pid_file"; do
    if [[ -f "$pid_file" ]]; then
      pid="$(cat "$pid_file")"
      if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
      rm -f "$pid_file"
    fi
  done
}

start_detached() {
  local pid_file="$1"
  local log_file="$2"
  shift 2
  if command -v setsid >/dev/null 2>&1; then
    nohup setsid "$@" >"$log_file" 2>&1 &
  else
    nohup "$@" >"$log_file" 2>&1 &
  fi
  echo "$!" >"$pid_file"
}

safe_reset_target() {
  local target="$1"
  case "$target" in
    ./var/*|var/*)
      ;;
    *)
      if [[ "${DEMO_ALLOW_CUSTOM_RESET:-0}" != "1" ]]; then
        echo "Refusing to reset target outside ./var: $target" >&2
        echo "Set DEMO_ALLOW_CUSTOM_RESET=1 only if this is an isolated generated-demo vault." >&2
        exit 2
      fi
      ;;
  esac
  if [[ "$target" == "/" || -z "$target" ]]; then
    echo "Refusing unsafe replay target: $target" >&2
    exit 2
  fi
  rm -rf "$target"
  mkdir -p "$target"
}

export VAULT_PATH="$target_vault"
export REPLAY_TARGET_VAULT="$target_vault"
export REPLAY_STATE_DIR="$target_vault"

mkdir -p "$state_dir" "$log_dir" "$target_vault"

echo "Using compose file: $compose_file"
echo "Using env file: $env_file"
echo "Using generated source: $source_vault"
echo "Using isolated replay target: $target_vault"
echo "Using replay speed: $speed virtual seconds per real second"
echo "Using replay batch size: $batch_size"
echo "Using scheduler interval: $scheduler_interval seconds"

"${compose[@]}" config >/dev/null

if [[ "$reset" == "1" ]]; then
  stop_background_processes
  safe_reset_target "$target_vault"
  recreate_vault_services=1
else
  stop_background_processes
  recreate_vault_services=0
fi

"${compose[@]}" up -d postgres
if [[ "$recreate_vault_services" == "1" ]]; then
  "${compose[@]}" up -d --force-recreate vault-obsidian mcp postgres-browser replay-dashboard replay-qa
else
  "${compose[@]}" up -d vault-obsidian mcp postgres-browser replay-dashboard replay-qa
fi

echo "Seeding replay target with $initial_limit note(s) before first ingest/dbt cycle."
"$python_bin" -m obsidian_mcp_context.replay_loader \
  --source "$source_vault" \
  --target "$target_vault" \
  --limit "$initial_limit" \
  --speed 0 \
  --batch-size "$initial_limit" \
  >"$log_dir/initial-replay.log" 2>&1

printf -v target_vault_q "%q" "$target_vault"
printf -v env_file_q "%q" "$env_file"
printf -v compose_file_q "%q" "$compose_file"
ingest_command="VAULT_PATH=$target_vault_q REPLAY_TARGET_VAULT=$target_vault_q docker compose --env-file $env_file_q -f $compose_file_q run --rm ingest"
dbt_command="VAULT_PATH=$target_vault_q REPLAY_TARGET_VAULT=$target_vault_q docker compose --env-file $env_file_q -f $compose_file_q run --rm dbt"

echo "Running initial ingest/dbt cycle."
"$python_bin" -m obsidian_mcp_context.replay_scheduler \
  --vault "$target_vault" \
  --ingest-command "$ingest_command" \
  --dbt-command "$dbt_command" \
  --interval-seconds "$scheduler_interval" \
  --once \
  >"$log_dir/initial-scheduler.log" 2>&1

if [[ "$start_dbt_docs" == "1" ]]; then
  "${compose[@]}" up -d dbt-docs
fi

if [[ "$continuous" == "1" ]]; then
  echo "Starting background replay and scheduler loops."
  start_detached "$replay_pid_file" "$log_dir/replay.log" \
    "$python_bin" -m obsidian_mcp_context.replay_loader \
    --source "$source_vault" \
    --target "$target_vault" \
    --speed "$speed" \
    --batch-size "$batch_size"

  start_detached "$scheduler_pid_file" "$log_dir/scheduler.log" \
    "$python_bin" -m obsidian_mcp_context.replay_scheduler \
    --vault "$target_vault" \
    --ingest-command "$ingest_command" \
    --dbt-command "$dbt_command" \
    --interval-seconds "$scheduler_interval"
fi

if [[ "$start_dbt_docs" == "1" ]]; then
  dbt_docs_line="dbt docs:         http://localhost:$(env_value DBT_DOCS_PORT 8081)"
else
  dbt_docs_line="dbt docs:         skipped (--no-dbt-docs)"
fi

cat <<EOF
Synthetic generated-$size demo is running.

Open:
  Obsidian webtop:  http://localhost:$(env_value OBSIDIAN_WEB_PORT 3000)
  MCP HTTP:         http://localhost:$(env_value MCP_PORT 8000)
  $dbt_docs_line
  Postgres browser: http://localhost:$(env_value POSTGRES_BROWSER_PORT 8082)
  Replay dashboard: http://localhost:$(env_value REPLAY_DASHBOARD_PORT 8083)
  Replay Q&A:       http://localhost:$(env_value REPLAY_QA_PORT 8084)

State:
  Replay vault:     $target_vault
  Logs:             $log_dir
  Replay state:     $target_vault/.obsidian-mcp-replay-state.json
  Scheduler state:  $target_vault/.obsidian-mcp-scheduler-state.json

Lifecycle:
  scripts/run_synthetic_demo.sh status
  scripts/run_synthetic_demo.sh stop
EOF
