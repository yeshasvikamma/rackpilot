"""
solver/model.py — the deterministic CP-SAT solver.  (STUB — Dev A)

This is Layer 2: OR-Tools CP-SAT, no LLM, no network. It is the ONLY place in
RackPilot where decisions are made. It takes a reconciled `ConstraintSpec` and
returns a `SolverResult` that holds the placements, the Pareto frontier, the
violations, and — when infeasible — the IIS proof.

The real implementation lives on branch `solver`. On `main` this raises so the
3 gates in test_solver.py are xfail (expected-fail), keeping main green.

Build order (see solver/CLAUDE.md): feasibility -> IIS -> incremental re-solve -> Pareto.
"""

from __future__ import annotations

from contracts import ConstraintSpec, SolverResult


def solve(spec: ConstraintSpec) -> SolverResult:
    """
    Solve all four resource constraints (power N+1, thermal, fabric, space)
    simultaneously for the given ConstraintSpec and return a SolverResult.

    - If a feasible placement exists: status="feasible", populated placements and
      pareto_plans.
    - If not: status="infeasible", with violations and a non-empty `iis` proving
      the minimal conflicting set.

    Deterministic: same spec in → same result out.

    Args:
        spec: Contract A, the reconciled problem from Layer 1.

    Returns:
        Contract B, the solver's answer.
    """
    raise NotImplementedError(
        "Real CP-SAT solver is implemented on branch `solver`. "
        "During development the API runs against api/mock_solver.py instead."
    )
