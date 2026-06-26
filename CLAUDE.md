# RackPilot — Root CLAUDE.md (shared law)

## What this is

RackPilot is a capacity-engineering co-pilot for datacenters. A capacity engineer
decides where to place racks of hardware across four always-scarce resources:
**power** (with N+1 redundancy — load must survive one feed failing), **thermal/
cooling** (per-row heat budget), **network fabric** (port capacity + oversubscription
ratio), and **physical space** (contiguous rack units + floor weight). The hard part
is solving all four *simultaneously*, and re-solving every time the infrastructure
changes (a new chip like OpenAI's Jalapeño at 40kW+/rack, a feed derate, a cooling
unit dropping). Existing DCIM tools check constraints one at a time on clean data;
RackPilot solves them jointly, from conflicting inputs, re-run on every change, with
a human approving every action.

## The three layers — only the middle one decides

- **Layer 1 (agents):** read multiple *disagreeing* data sources, reconcile them into
  one `ConstraintSpec`, tagging each constraint with confidence + provenance (trusted
  source → hard constraint; stale/uncertain → soft constraint with a penalty).
- **Layer 2 (solver, NO LLM):** OR-Tools CP-SAT. Deterministic. Does ALL correctness.
  Three techniques: (a) multi-objective **Pareto** set, (b) incremental **warm-start**
  re-solve on change, (c) **IIS** = irreducible infeasible subset when no solution exists.
- **Layer 3 (agents):** when infeasible, agents that each own a constraint class
  negotiate which rule bends, surfacing dissent to the human.

## The two contracts (`contracts.py`)

- **Contract A — `ConstraintSpec`:** the reconciled problem the agents hand to the solver.
- **Contract B — `SolverResult`:** the deterministic answer the solver hands back.

**`contracts.py` is shared law.** It is the only file both branches share. **Never edit
`contracts.py` on one branch without syncing with the other dev** — a contract change is
the *only* thing that can break the merge, because both halves are compiled against these
shapes. Need a new field? Stop, have the contract conversation, change it together.

## Ownership (by directory → clean merges)

| Developer | Branch    | Owns                  | Rules |
|-----------|-----------|-----------------------|-------|
| **Dev A** | `solver`  | `data/`, `solver/`    | Pure Python. No network, no LLM. Consumes `ConstraintSpec`, produces `SolverResult`. |
| **Dev B** | `agents`  | `agents/`, `api/`, `ui/` | All LLM + API + frontend. Produces `ConstraintSpec`, consumes `SolverResult`. |
| **shared**| (sync)    | `contracts.py`        | Edited only jointly. |

Ownership is **by directory** so the two branches almost never touch the same file.

## Branch workflow

- `main` is the base. Dev A works on branch `solver`, Dev B works on branch `agents`.
- Each works ONLY in their owned directories.
- Pull `main` before pushing. Commit small and often.
- Because ownership is by directory, git should find **no conflicts outside `contracts.py`**.

## The merge procedure

During development, `api/main.py` imports the solver like this:

```python
from api.mock_solver import solve     # dev-time stand-in (working, hardcoded)
```

The **entire final integration is changing that ONE import** to:

```python
from solver.model import solve        # the real CP-SAT solver
```

Then: run the full `/handle` flow end to end, confirm the **break moment** fires through
the *real* solver (the feed derate re-solve produces the expected `newly_violating`), then
build the `Dockerfile` and publish.

## The golden rule

**The SOLVER decides everything. LLMs only assemble the problem and explain results.**
Never let an agent make a placement decision. If a placement, a violation, an IIS, or a
Pareto trade-off is being *decided*, it happens in `solver/`, deterministically — never in
an agent prompt.

## Scope-cut order (if time runs short)

Cut in this order, and **only** in this order:

1. Cut the **forecaster** first.
2. Then simplify **Layer 3** (the negotiation).
3. Then drop **Pareto** to a single objective.

**NEVER cut:** the **break moment**, the **IIS proofs**, the **human approval gate**.
These three are the demo.

## Running it

```bash
pip install -r requirements.txt
pytest                      # main is green: the 3 solver gates are xfail (expected-fail)
uvicorn api.main:app --reload   # dev API, runs against api/mock_solver.py
```
