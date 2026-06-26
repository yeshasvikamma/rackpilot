# solver/ — Dev A (branch `solver`)

**You own this directory.** This is Layer 2. **No LLM calls, no network.** OR-Tools
CP-SAT only. The solver does **all** correctness — it decides everything.

You **consume `ConstraintSpec` and produce `SolverResult`** per `contracts.py`.
**Do not change those shapes here** — a contract change is a joint decision with Dev B.
**Do not touch `agents/`, `api/`, or `ui/`.**

## Definition of done

The **3 tests in `solver/test_solver.py` passing.** They are `xfail` on `main`; when your
real solver makes them pass, remove the `xfail` marks — that is Track A done.

1. `test_place_batch` — 8x 40kW N+1 → feasible, all placements in Pod C, pods A and B
   appear in violations, IIS non-empty.
2. `test_break` — healthy facility + feed derate → `facility_diff.newly_violating ==
   ["r_113", "r_118", "r_124"]` exactly.
3. `test_pareto` — `pareto_plans` has 3 entries, none dominating another.

## Solver technique priority (build in THIS order)

1. **Feasibility first.** Get a single correct placement honoring all four resources
   simultaneously (power N+1, thermal per-row, fabric ports + oversub, space contiguous
   U + floor weight). Nothing else matters until this is solid.
2. **IIS** — when infeasible, compute the irreducible infeasible subset: the minimal set
   of constraints that conflict. This is the proof Layer 3 negotiates over. Non-negotiable
   for the demo.
3. **Incremental re-solve** — warm-start from the previous solution when a `ChangeEvent`
   arrives, and diff against the prior facility version (this powers the break moment).
4. **Pareto** — only after the above: produce the multi-objective non-dominated set.
   This is the first thing to drop to single-objective if time runs short.

Determinism is mandatory: same `ConstraintSpec` → same `SolverResult`, every run.
