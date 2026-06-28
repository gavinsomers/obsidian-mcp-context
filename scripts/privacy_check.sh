#!/usr/bin/env bash
set -euo pipefail

LOCAL_TERMS_FILE=".privacy-banned-terms.local"
ERRORS=0

CORE_PATH_PATTERNS=(
  '*.duckdb'
  '*.duckdb.wal'
  'var/*'
)

LOCAL_TERMS=()
if [[ -f "$LOCAL_TERMS_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    clean_line="$(printf '%s' "$line" | sed 's/#.*//' | xargs)"
    if [[ -n "$clean_line" ]]; then
      LOCAL_TERMS+=("$clean_line")
    fi
  done < "$LOCAL_TERMS_FILE"
fi

mapfile -t STAGED_FILES < <(git diff --cached --name-only --diff-filter=ACMRT)

for file in "${STAGED_FILES[@]}"; do
  for pattern in "${CORE_PATH_PATTERNS[@]}"; do
    if [[ "$file" == $pattern ]]; then
      printf 'ERROR: Staged file path "%s" matches blocked pattern "%s".\n' "$file" "$pattern" >&2
      ERRORS=$((ERRORS + 1))
    fi
  done

  for term in "${LOCAL_TERMS[@]}"; do
    if grep -Fqi -- "$term" <<< "$file"; then
      printf 'ERROR: Staged file path "%s" contains local sensitive term "%s".\n' "$file" "$term" >&2
      ERRORS=$((ERRORS + 1))
    fi
  done

  if git diff --cached --numstat -- "$file" | awk '$1 == "-" || $2 == "-" { found = 1 } END { exit !found }'; then
    continue
  fi

  staged_added_lines="$(git diff --cached -U0 -- "$file" | sed -n 's/^+//p')"

  for term in "${LOCAL_TERMS[@]}"; do
    if grep -Fqi -- "$term" <<< "$staged_added_lines"; then
      printf 'ERROR: Staged changes in "%s" contain local sensitive term "%s".\n' "$file" "$term" >&2
      ERRORS=$((ERRORS + 1))
    fi
  done
done

if [[ "$ERRORS" -gt 0 ]]; then
  printf 'Commit blocked by privacy guardrails. Remove the sensitive patterns or unstage the files.\n' >&2
  exit 1
fi

printf 'Privacy check passed.\n'
