# RackPilot

A capacity-engineering co-pilot for datacenters. It places racks of hardware against four
always-scarce resources — **power** (N+1 redundant), **thermal/cooling**, **network fabric**,
and **physical space** — by solving all four *simultaneously*, and re-solving on every
infrastructure change, with a human approving every action.

Three layers, and **only the middle one makes decisions**:

1. **Agents (Layer 1)** reconcile disagreeing data sources into one `ConstraintSpec`.
2. **Solver (Layer 2, no LLM)** — OR-Tools CP-SAT, deterministic — does all correctness:
   Pareto trade-offs, incremental warm-start re-solve, and IIS proofs when infeasible.
3. **Agents (Layer 3)** negotiate which rule bends when no plan exists, surfacing dissent
   to the human.

See [`CLAUDE.md`](./CLAUDE.md) for the full project law (contracts, ownership, golden rule).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in GMI_API_KEY and GMI_BASE_URL
```

## Run the tests

```bash
pytest
```

`main` is **green**. The three solver gates in `solver/test_solver.py` are marked
`xfail` (expected-fail) until Dev A's real solver lands — they encode the definition of
done for the solver track, not failures.

## Run the dev API

```bash
uvicorn api.main:app --reload
# POST http://127.0.0.1:8000/handle
```

During development the API runs against `api/mock_solver.py`, a working hardcoded
`SolverResult`. This is what lets Dev B build the entire agents + api + ui half without
ever waiting for the real solver.

## Ownership

| Developer | Branch   | Owns                     |
|-----------|----------|--------------------------|
| Dev A     | `solver` | `data/`, `solver/`       |
| Dev B     | `agents` | `agents/`, `api/`, `ui/` |
| shared    | (sync)   | `contracts.py`           |

Ownership is by directory, so the two branches almost never touch the same file → clean
merges. **`contracts.py` is the only shared file — never edit it on one branch alone.**

## The merge procedure

1. Both branches develop independently in their own directories.
2. Dev B builds against `from api.mock_solver import solve`.
3. **Final integration is a one-line swap** in `api/main.py`:
   `from api.mock_solver import solve` → `from solver.model import solve`.
4. Run the full `/handle` flow, confirm the break moment fires through the **real** solver
   (the feed-derate re-solve yields the expected `newly_violating` set).
5. Build the `Dockerfile`, publish.

## Scope-cut order (if time runs short)

Cut **forecaster** first → then simplify **Layer 3** → then drop **Pareto** to single-objective.
**Never cut** the break moment, the IIS proofs, or the human approval gate.
