# Demo Privacy Readiness

Use this checklist before recording demos, screenshots, talks, or marketing
material for this repo.

## Boundary

The public demo workflow uses generated/synthetic vaults only:

- `examples/generated-vaults/small`
- `examples/generated-vaults/medium`
- `examples/generated-vaults/large`
- `examples/synthetic-vault`

Gavin's personal Obsidian vault is out of scope for demo validation, screenshots,
fixtures, tests, docs, generated outputs, and MCP serving examples.

## Defaults

- `.env.analytics.example` points to `./examples/synthetic-vault`.
- `scripts/analytics_stack_check.sh small|medium|large` overrides `VAULT_PATH`
  with checked-in generated fixtures.
- `scripts/run_synthetic_demo.sh` accepts only `small`, `medium`, or `large` and
  replays into ignored `var/replay-vault` storage.
- `scripts/run_generated_obsidian.sh` accepts only generated fixture sizes or the
  checked-in synthetic fixture.
- `doctor` diagnostic samples are redacted by default.
- Runtime state lives under ignored `var/`, `logs/`, and `target/` paths.
- Local config and sensitive-term files are ignored:
  `.env.analytics`, `.obsidian-mcp-context.toml`, and
  `.privacy-banned-terms.local`.

## Validation

Run these before demo capture:

```bash
scripts/privacy_check.sh --all
scripts/run_synthetic_demo.sh small --fast
scripts/check_synthetic_demo.sh --skip-dbt-docs
```

Use `scripts/run_synthetic_demo.sh stop` after validation if the demo stack does
not need to stay running.

## Caveats

Private local vault experiments are allowed only outside the demo workflow. Keep
private paths in ignored local config files, write diagnostics under ignored
runtime directories such as `var/`, and do not commit or publish screenshots,
exports, or logs produced from private vault content.
