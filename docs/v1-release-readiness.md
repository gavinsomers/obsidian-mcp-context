# v1.0 Release Readiness

This checklist defines what must be true before tagging `v1.0.0`.

The v1.0 claim is narrow:

> `obsidian-mcp-context` turns generated Obsidian-style vault fixtures into
> structured, source-linked Postgres/dbt marts and exposes that modeled context
> through MCP and local demo surfaces.

The v1.0 claim is not:

- a hosted product
- a cloud compiler
- a personal-vault sync product
- an automatic AI editing system
- a guarantee that arbitrary private vaults are safe or useful without local
  profiling and review

## Required Gates

### 1. Version And Release Notes

- [ ] `pyproject.toml` has the target version.
- [ ] `obsidian_mcp_context/__init__.py` has the same `__version__`.
- [ ] `CHANGELOG.md` has a dated `v1.0.0` entry.
- [ ] `RELEASING.md` release commands use the actual target tag.
- [ ] The release PR title and changelog describe generated-vault scope, not a
      personal-vault product.

Verify:

```bash
.venv/bin/pytest tests/test_version.py -q
```

Expected:

```text
1 passed
```

### 2. Local Install Path

- [ ] A fresh checkout can create a virtualenv.
- [ ] Editable install works with dev and pipeline extras.
- [ ] Console scripts are available.

Verify:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,pipeline]"
.venv/bin/obsidian-mcp-context --help
.venv/bin/obsidian-mcp-context-mcp --help
.venv/bin/obsidian-mcp-context-ingest-postgres --help
```

Expected:

```text
usage:
```

for each CLI entry point.

### 3. Unit And Contract Tests

- [ ] Python tests pass.
- [ ] Shell scripts parse.
- [ ] Package modules compile.
- [ ] JSON eval packs parse.

Verify:

```bash
bash -n scripts/*.sh
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall obsidian_mcp_context
python3 -m json.tool examples/eval-packs/generated-demo.json >/tmp/generated-demo.valid
python3 -m json.tool examples/eval-packs/consultancy-demo.json >/tmp/consultancy-demo.valid
```

Expected:

```text
passed
```

from pytest and no shell, compile, or JSON parser errors.

### 4. Privacy And Generated-Data Boundary

- [ ] Full tracked-file privacy scan passes.
- [ ] Local runtime/config files remain ignored.
- [ ] Demo and marketing docs state generated/synthetic-only scope.
- [ ] No personal vault paths, screenshots, generated outputs, or diagnostics
      are committed.

Verify:

```bash
scripts/privacy_check.sh --all
.venv/bin/pytest tests/test_privacy_check.py tests/test_privacy_ignore_rules.py -q
```

Expected:

```text
Privacy check passed.
```

and all privacy tests pass.

### 5. Generated Fixture Validation

- [ ] Static generated fixtures pass parser/warehouse contract tests.
- [ ] Reconciliation tests pass against expected generated-vault behavior.
- [ ] Generated fixtures remain synthetic and safe for public demo use.

Verify:

```bash
.venv/bin/pytest tests/test_synthetic_vault.py tests/test_generated_consultancy_acceptance.py -q
```

Expected:

```text
passed
```

### 6. Postgres/dbt/MCP Stack

- [ ] Postgres container stack builds.
- [ ] Ingest writes raw tables.
- [ ] dbt builds marts.
- [ ] dbt tests pass.
- [ ] Postgres-backed MCP smoke checks return modeled rows.

Fast verification:

```bash
scripts/run_dataset_workflow.sh small
```

Release verification:

```bash
scripts/run_dataset_workflow.sh large
```

Expected:

```text
Dataset workflow passed.
```

### 7. Completed Dataset Demo Readiness

- [ ] Completed generated-small workflow runs without personal vault input.
- [ ] MCP starts against the dbt-built marts.
- [ ] dbt Docs is available on demand for lineage proof.
- [ ] Postgres browser is available on demand for raw/mart row inspection.
- [ ] Representative prompts can be asked through an MCP client against the
      completed dataset.

Verify:

```bash
scripts/run_dataset_workflow.sh small --with-inspection
```

Expected:

```text
Dataset workflow passed.
```

Stop the demo after validation unless it is needed:

```bash
docker compose --env-file .env.analytics.example -f docker-compose.analytics.yml down
```

### 8. MCP Client Setup

- [ ] `docs/mcp-client-setup.md` has a generated-vault-only setup path.
- [ ] MCP docs distinguish mart-backed tools from parser diagnostics.
- [ ] `get_vault_context_preset` is documented as the normal agent-facing
      entry point.
- [ ] Fallback parser diagnostics are described as troubleshooting, not a
      successful modeled-context setup.

Verify docs manually:

```text
docs/mcp-client-setup.md
README.md#MCP Tools
```

### 9. Public Claims

Marketing/demo material may claim:

- generated Obsidian-style notes can be compiled into structured marts
- Postgres/dbt provides inspectable contracts for context
- MCP tools can retrieve project, person, decision, risk, open-loop, and preset
  context from modeled marts
- the public demo does not require Gavin's personal vault
- optional AI steps are advisory and not part of canonical note mutation

Marketing/demo material must not claim:

- production hosted deployment
- private-vault safety without local review
- automatic note editing
- universal semantic understanding
- guaranteed retrieval quality on arbitrary vaults
- customer/client proof beyond generated fixtures

## Known Limitations Accepted For v1.0

- The public demo uses generated/synthetic fixtures only.
- Local-private vault experiments are allowed outside the demo workflow but are
  not part of the v1.0 release claim.
- The `open risks` wording can route to both risk and open-loop retrieval
  because `open` is part of the open-loop intent vocabulary. Use the wording in
  `docs/retrieval-validation.md` for demos.
- Hosted AI providers remain opt-in and gated by privacy settings.
- The analytics stack check is the release-quality end-to-end proof; routine CI
  still runs the Python suite and privacy checks by default.

## Existing Follow-Up Coverage

These items are not v1.0 blockers unless the release owner decides to broaden
the release claim:

| Follow-up | Trello card | Release stance |
| --- | --- | --- |
| MCP access-boundary narrative | `Document MCP access boundaries` | Useful public-doc polish; not a blocker if generated-only scope remains clear. |
| Local power-user hardening | `Harden local power-user vault workflow` | Post-v1 local usability work, not part of generated-demo v1 claim. |
| Advisory AI review lifecycle | `Define advisory AI enrichment review loop` | Needed before stronger AI-governance claims; not required for deterministic demo. |
| Context capture template | `Create context capture template` | Useful for operating discipline, not required for generated fixture release. |

## Release Decision

Before tagging `v1.0.0`, the release owner should mark each required gate as
pass, fail, or intentionally deferred in the release PR description. Any failed
gate must either block the tag or be converted into a separate card with the v1
claim adjusted accordingly.
