#!/usr/bin/env bash
set -euo pipefail

LOCAL_TERMS_FILE=".privacy-banned-terms.local"
ERRORS=0
MODE="staged"

CORE_PATH_PATTERNS=(
  '.env.analytics'
  '.obsidian-mcp-context.toml'
  '.privacy-banned-terms.local'
  '*.duckdb'
  '*.duckdb.wal'
  'var/*'
)

usage() {
  cat <<'EOF'
Usage:
  scripts/privacy_check.sh [--staged|--all]

Checks staged changes by default. Use --all before demos or releases to scan
all tracked files for blocked runtime artifacts and local sensitive terms.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged)
      MODE="staged"
      shift
      ;;
    --all)
      MODE="all"
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

LOCAL_TERMS=()
if [[ -f "$LOCAL_TERMS_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    clean_line="$(printf '%s' "$line" | sed 's/#.*//' | xargs)"
    if [[ -n "$clean_line" ]]; then
      LOCAL_TERMS+=("$clean_line")
    fi
  done < "$LOCAL_TERMS_FILE"
fi

if [[ "$MODE" == "all" ]]; then
  mapfile -t CHECKED_FILES < <(git ls-files)
else
  mapfile -t CHECKED_FILES < <(git diff --cached --name-only --diff-filter=ACMRT)
fi

for file in "${CHECKED_FILES[@]}"; do
  for pattern in "${CORE_PATH_PATTERNS[@]}"; do
    if [[ "$file" == $pattern ]]; then
      printf 'ERROR: Checked file path "%s" matches blocked pattern "%s".\n' "$file" "$pattern" >&2
      ERRORS=$((ERRORS + 1))
    fi
  done

  for term in "${LOCAL_TERMS[@]}"; do
    if grep -Fqi -- "$term" <<< "$file"; then
      printf 'ERROR: Checked file path "%s" contains local sensitive term "%s".\n' "$file" "$term" >&2
      ERRORS=$((ERRORS + 1))
    fi
  done

  if [[ "$MODE" == "all" ]]; then
    if [[ -f "$file" ]] && grep -Iq . "$file"; then
      checked_text="$(cat "$file")"
    else
      checked_text=""
    fi
  else
    if git diff --cached --numstat -- "$file" | awk '$1 == "-" || $2 == "-" { found = 1 } END { exit !found }'; then
      continue
    fi

    checked_text="$(git diff --cached -U0 -- "$file" | sed -n 's/^+//p')"
  fi

  for term in "${LOCAL_TERMS[@]}"; do
    if [[ -n "$checked_text" ]] && grep -Fqi -- "$term" <<< "$checked_text"; then
      printf 'ERROR: Checked content in "%s" contains local sensitive term "%s".\n' "$file" "$term" >&2
      ERRORS=$((ERRORS + 1))
    fi
  done
done

if [[ "$ERRORS" -gt 0 ]]; then
  printf 'Commit blocked by privacy guardrails. Remove the sensitive patterns or unstage the files.\n' >&2
  exit 1
fi

printf 'Privacy check passed.\n'
