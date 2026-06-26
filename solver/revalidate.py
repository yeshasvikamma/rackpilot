"""
solver/revalidate.py — incremental re-solve on change.  (STUB — Dev A)

The break moment. When infrastructure changes (a feed derate, a cooling unit
dropping, a new higher-power chip), revalidate warm-starts from the previous
solution, re-solves, and reports what newly violates against the prior facility
version.

Pure Python on top of CP-SAT. No LLM, no network. Deterministic.

The real implementation lives on branch `solver`. Signature only here.
"""

from __future__ import annotations

from contracts import ConstraintSpec, SolverResult


def revalidate(
    spec: ConstraintSpec,
    previous: SolverResult,
) -> SolverResult:
    """
    Re-solve the facility after a `ChangeEvent` (carried on `spec.change_event`),
    warm-starting from `previous`, and return an updated SolverResult whose
    `facility_diff.newly_violating` lists the racks that broke as a result.

    For the demo's feed-derate scenario this must yield
    newly_violating == ["r_113", "r_118", "r_124"].

    Args:
        spec:     Contract A in mode "revalidate", carrying the change_event.
        previous: the SolverResult from before the change (for warm-start + diff).

    Returns:
        Contract B, the re-solved result including the facility_diff.
    """
    raise NotImplementedError(
        "Incremental revalidate is implemented on branch `solver`."
    )
