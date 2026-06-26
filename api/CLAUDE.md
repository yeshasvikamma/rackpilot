# api/ — Dev B (branch `agents`)

**You own this directory.** This is the orchestration seam between the agents and the solver.

You **produce `ConstraintSpec` and consume `SolverResult`** per `contracts.py`.
**Do not change those shapes here** — a contract change is a joint decision with Dev A.
**Do not touch `data/` or `solver/`.**

## The one rule that makes the merge trivial

`main.py` imports the solver from the **mock** during development:

```python
from api.mock_solver import solve     # working, hardcoded SolverResult
```

The **entire final integration is changing that one line** to:

```python
from solver.model import solve        # the real CP-SAT solver
```

Build everything against the mock. `api/mock_solver.py` returns a fully-populated,
schema-valid `SolverResult` — it is what unblocks the whole agents + api + ui half. Never
block on the real solver.

## Orchestration is hardcoded Python, NOT an LLM

The `/handle` flow runs agents in a **fixed Python sequence**. The LLM never decides what
runs next, and **never makes a placement decision** — the solver decides everything.
Typical flow:

1. read sources → `reconcile(...)` → `ConstraintSpec`  (Layer 1)
2. `solve(spec)` → `SolverResult`                        (Layer 2 — the only decider)
3. `explain(result)`, `critique(result, plan)`          (Layer 3)
4. return everything to the human for approval           (the approval gate)

## Model assignments

See `agents/CLAUDE.md` for the role→model table (reconciler → Nemotron 3 Super,
source-readers → Nemotron 3 Nano, explainer → GPT-5.4 / Nemotron Super fallback,
risk → DeepSeek-V4-Pro, forecaster → Nemotron 3 Super). GMI is OpenAI-compatible.
