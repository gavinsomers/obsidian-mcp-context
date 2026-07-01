#!/usr/bin/env bash
set -euo pipefail

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

exec "$python_bin" -m obsidian_mcp_context.synthetic_demo_health "$@"
