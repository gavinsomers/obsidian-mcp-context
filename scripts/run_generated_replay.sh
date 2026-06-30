#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.analytics.yml}"
vault_size="${1:-large}"
if [[ $# -gt 0 ]]; then
  shift
fi

if [[ -n "${ENV_FILE:-}" ]]; then
  env_file="$ENV_FILE"
elif [[ -f ".env.analytics" ]]; then
  env_file=".env.analytics"
else
  env_file=".env.analytics.example"
fi

case "$vault_size" in
  small|medium|large)
    source_vault="./examples/generated-vaults/$vault_size"
    ;;
  *)
    echo "Unknown vault size: $vault_size" >&2
    echo "Use one of: small, medium, large" >&2
    exit 2
    ;;
esac

target_vault="${REPLAY_TARGET_VAULT:-./var/replay-vault}"
export VAULT_PATH="$target_vault"

compose=(docker compose --env-file "$env_file" -f "$compose_file")
web_port="$(
  grep -E '^OBSIDIAN_WEB_PORT=' "$env_file" 2>/dev/null | tail -n1 | cut -d= -f2-
)"
web_port="${OBSIDIAN_WEB_PORT:-${web_port:-3000}}"

mkdir -p "$target_vault"

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

echo "Using compose file: $compose_file"
echo "Using env file: $env_file"
echo "Using replay source: $source_vault"
echo "Using isolated replay target: $target_vault"

"${compose[@]}" config >/dev/null
"${compose[@]}" up -d vault-obsidian

cat <<EOF
Browser Obsidian is running against the isolated replay target.

Open:
  http://localhost:$web_port

Inside the browser desktop, open /vault. Notes will appear there as the replay
loader copies generated fixture files into $target_vault.
EOF

"$python_bin" -m obsidian_mcp_context.replay_loader \
  --source "$source_vault" \
  --target "$target_vault" \
  "$@"
