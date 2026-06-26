# ui/ — Dev B (branch `agents`)

**You own this directory.** The single-screen facility board the engineer looks at.

You **consume `SolverResult`** (via the `/handle` API) per `contracts.py`.
**Do not change those shapes here** — a contract change is a joint decision with Dev A.
**Do not touch `data/` or `solver/`.**

## What the board shows

One screen. It renders a `SolverResult` and drives the human approval gate:

- **The facility** — pods (A, B, C), rows, enclosures; placements highlighted.
- **The Pareto plans** — the 3 trade-off options side by side; the human picks one.
- **Violations & the IIS proof** — why pods break, and the minimal conflicting set in
  plain language (from the explainer).
- **The break moment** — when a re-solve fires, flash the `facility_diff.newly_violating`
  racks so the regression is unmistakable.
- **Approve / reject** — the human is in the loop on every action. Nothing auto-applies.

## How it gets data

POST to `/handle` (see `api/main.py`). During development that endpoint runs against
`api/mock_solver.py`, so the board has a full, believable `SolverResult` to render from
day one — never block on the real solver. `board.html` is a placeholder to build out.
