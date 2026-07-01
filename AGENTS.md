# Repo Agent Instructions

## Trello Workflow

For this repository, keep the Trello board synchronized with implementation work.
Use the Trello MCP tools for Trello updates; do not use browser automation for
board/card changes.

Board: `Reporting Trust Project`

Before starting implementation:

- Find the relevant Trello card for the requested work.
- If a matching card exists, move it to `In Progress`.
- If no matching card exists, create one in `In Progress`.
- Add or comment the branch name, scope, and acceptance target.
- When creating or materially reshaping a Trello card, make sure the card
  description includes these sections:
  - `Driver`: why this work matters now, including strategic/product/reputation
    context where relevant.
  - `Scope`: what is included in this card.
  - `Out of scope`: explicit boundaries and tempting adjacent work not included.
  - `Acceptance target`: the observable finish condition.

When opening a pull request:

- Add the PR URL to the Trello card.
- Comment with the tests run and any runtime caveats.
- Move the card to `Review`.

When Gavin says the pull request is merged:

- Sync local `main`.
- Add a merge-status comment to the Trello card.
- Move the card to `Done`.
- If follow-up work is discovered, create a separate card in `Next` or
  `In Progress` instead of leaving the merged card open.

Before the final response for completed work:

- Check the related Trello card is in the correct list.
- Check `In Progress` and `Review` for stale cards related to the current work.
- Mention any Trello card movement in the final response.
