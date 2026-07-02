# Retrieval Validation

This note defines the current representative prompt set for demoing the
generated-vault MCP/context layer.

## Source

The default smoke-test prompt pack is:

```text
examples/eval-packs/generated-demo.json
```

The stricter demo-readiness prompt pack is:

```text
examples/eval-packs/consultancy-demo.json
```

Run the completed generated-small workflow before using these prompts through
an MCP client:

```bash
scripts/run_dataset_workflow.sh small --with-inspection
```

Both packs use generated/synthetic vault context only.

## Prompt Set

| Prompt id | Prompt | Retrieval behavior proved |
| --- | --- | --- |
| `atlas-risks-open-loops` | What are the risks and open loops for Project Atlas 1? | Resolves an exact project entity and retrieves both risk rows and open-loop/task rows with source paths. |
| `atlas-decisions` | What decisions have been made for Project Atlas 1? | Routes decision intent to decision rows and keeps source-linked decision provenance. |
| `atlas-full-context` | What is the full Project Atlas 1 context? | Falls back to broad project context when no narrow risk/decision/open-loop intent is present. |
| `atlas-stakeholder-brief` | What should I brief Alex Alvarez on before the Project Atlas 1 check-in? | Handles a realistic stakeholder-prep question while resolving the project entity from the question. |
| `beacon-risks` | What risks are open for Project Beacon 2? | Proves the same risk retrieval pattern works for a second project. |
| `beacon-latest-context` | What is the latest context for Project Beacon 2? | Proves broad context retrieval for a second project. |

## Current Result

The completed-dataset path should cover:

- mart-backed mode, not parser fallback
- exact entity resolution for `Project Atlas 1` and `Project Beacon 2`
- source-linked decision, risk, daily-note, meeting, and task/open-loop rows
- enough sources per prompt to support a visible demo answer

## Caveat

The wording `open risks` can trigger both `risks` and `open_loops`
because `open` is also part of the open-loop intent vocabulary. For demo
material, prefer either:

- `What risks and open loops remain for ...?`
- `What risks exist for ...?`

Treat this as prompt-shaping guidance rather than a blocker. If stricter
intent separation becomes important, split that into a separate routing card.
