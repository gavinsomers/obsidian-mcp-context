#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_dataset_workflow.sh /path/to/generated-vault
  scripts/run_dataset_workflow.sh [small|medium|large|synthetic]

Run the quiet completed-dataset workflow:
  validate vault manifest, start Postgres, ingest the full vault, run dbt,
  run dbt tests, and start the MCP server.

Options:
  --help    Show this help.

Environment:
  ENV_FILE       Compose env file. Defaults to .env.analytics,
                 then .env.analytics.example.
  COMPOSE_FILE   Compose file. Default: docker-compose.analytics.yml.
EOF
}

compose_file="${COMPOSE_FILE:-docker-compose.analytics.yml}"
dataset_arg=""

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 2
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$dataset_arg" ]]; then
        echo "Unexpected extra argument: $1" >&2
        usage >&2
        exit 2
      fi
      dataset_arg="$1"
      shift
      ;;
  esac
done

if [[ -n "${ENV_FILE:-}" ]]; then
  env_file="$ENV_FILE"
elif [[ -f ".env.analytics" ]]; then
  env_file=".env.analytics"
else
  env_file=".env.analytics.example"
fi

case "$dataset_arg" in
  small|medium|large)
    dataset_path="./examples/generated-vaults/$dataset_arg"
    dataset_label="generated-$dataset_arg"
    ;;
  synthetic)
    dataset_path="./examples/synthetic-vault"
    dataset_label="synthetic"
    ;;
  *)
    dataset_path="$dataset_arg"
    dataset_label="$(basename "$dataset_path")"
    ;;
esac

if [[ ! -d "$dataset_path" ]]; then
  echo "Dataset path does not exist or is not a directory: $dataset_path" >&2
  exit 2
fi

if [[ ! -f "$dataset_path/manifest.json" ]]; then
  echo "Dataset manifest is missing: $dataset_path/manifest.json" >&2
  exit 2
fi

if [[ ! -f "$env_file" ]]; then
  echo "Compose env file does not exist: $env_file" >&2
  exit 2
fi

if [[ ! -f "$compose_file" ]]; then
  echo "Compose file does not exist: $compose_file" >&2
  exit 2
fi

if command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
elif command -v python >/dev/null 2>&1; then
  python_bin="python"
else
  echo "Could not find python. Install python3." >&2
  exit 127
fi

validation_json="$(
  "$python_bin" - "$dataset_path" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

vault = Path(sys.argv[1])
manifest_path = vault / "manifest.json"
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    raise SystemExit(f"Dataset manifest is not valid JSON: {exc}") from exc

markdown_count = sum(1 for path in vault.rglob("*.md") if path.is_file())
if markdown_count <= 0:
    raise SystemExit("Dataset contains no Markdown notes.")

counts = manifest.get("counts") if isinstance(manifest, dict) else None
manifest_note_count = None
if isinstance(counts, dict):
    manifest_note_count = counts.get("Total_Files") or counts.get("total_files")
if manifest_note_count is None and isinstance(manifest, dict):
    manifest_note_count = (
        manifest.get("note_count")
        or manifest.get("total_files")
        or manifest.get("Total_Files")
    )

payload = {
    "manifest_path": str(manifest_path),
    "markdown_count": markdown_count,
    "manifest_note_count": manifest_note_count,
    "profile": manifest.get("profile") if isinstance(manifest, dict) else None,
    "dataset_id": manifest.get("dataset_id") if isinstance(manifest, dict) else None,
    "completed": manifest.get("completed") if isinstance(manifest, dict) else None,
}
print(json.dumps(payload, sort_keys=True))
PY
)"

export VAULT_PATH
VAULT_PATH="$(cd "$dataset_path" && pwd -P)"

compose=(docker compose --env-file "$env_file" -f "$compose_file")
log_dir="logs/dataset-workflow"
mkdir -p "$log_dir"

env_value() {
  local key="$1"
  local default="$2"
  local value
  value="$(grep -E "^${key}=" "$env_file" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  printf '%s' "${!key:-${value:-$default}}"
}

run_logged() {
  local name="$1"
  shift
  local log_file="$log_dir/$name.log"
  if "$@" >"$log_file" 2>&1; then
    return 0
  fi

  echo "Step failed: $name" >&2
  echo "Log: $log_file" >&2
  echo >&2
  tail -n 80 "$log_file" >&2 || true
  return 1
}

echo "Dataset: $dataset_label"
echo "Vault: $VAULT_PATH"
echo "Compose file: $compose_file"
echo "Env file: $env_file"
echo "Logs: $log_dir"
echo

"$python_bin" - "$validation_json" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
manifest_count = payload.get("manifest_note_count")
manifest_suffix = ""
if manifest_count is not None:
    manifest_suffix = f", manifest_count={manifest_count}"
print(
    "[1/6] Validating dataset... passed "
    f"(notes={payload['markdown_count']}{manifest_suffix})"
)
PY

run_logged compose-config "${compose[@]}" config

echo "[2/6] Starting Postgres..."
run_logged postgres "${compose[@]}" up -d postgres
echo "[2/6] Starting Postgres... ready"

echo "[3/6] Ingesting vault into Postgres..."
run_logged ingest "${compose[@]}" run --rm ingest
echo "[3/6] Ingesting vault into Postgres... passed"

echo "[4/6] Running dbt models..."
run_logged dbt "${compose[@]}" run --rm dbt
echo "[4/6] Running dbt models... passed"

echo "[5/6] Running dbt tests..."
run_logged dbt-test "${compose[@]}" run --rm dbt-test
echo "[5/6] Running dbt tests... passed"

echo "[6/6] Starting MCP..."
run_logged mcp "${compose[@]}" up -d mcp
echo "[6/6] Starting MCP... ready"

cat <<EOF

Dataset workflow passed.

Open:
  MCP HTTP: http://localhost:$(env_value MCP_PORT 8000)
EOF
