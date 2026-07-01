#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.analytics.yml}"
vault_size="${1:-large}"

if [[ -n "${ENV_FILE:-}" ]]; then
  env_file="$ENV_FILE"
elif [[ -f ".env.analytics" ]]; then
  env_file=".env.analytics"
else
  env_file=".env.analytics.example"
fi

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

compose=(docker compose --env-file "$env_file" -f "$compose_file")
web_port="$(
  grep -E '^OBSIDIAN_WEB_PORT=' "$env_file" 2>/dev/null | tail -n1 | cut -d= -f2-
)"
web_port="${OBSIDIAN_WEB_PORT:-${web_port:-3000}}"

echo "Using compose file: $compose_file"
echo "Using env file: $env_file"
echo "Using vault path: $VAULT_PATH"

"${compose[@]}" config >/dev/null
"${compose[@]}" up -d vault-obsidian

cat <<EOF
Browser Obsidian is starting.

Open:
  http://localhost:$web_port

Obsidian auto-launches in the browser desktop and opens /vault.

This mounts the generated fixture vault only. It does not read or write Gavin's
personal Obsidian vault.
EOF
