"""
agents/risk.py — Layer 3 adversarial critique.  (STUB — Dev B)

A skeptic. Given the solver's result and a chosen plan, it argues the other side:
what could go wrong, which soft constraints were leaned on, where the provenance is
weak. It runs on a deliberately INDEPENDENT model family (DeepSeek-V4-Pro) so its
critique is not correlated with the reconciler/explainer — it is meant to disagree.

It critiques; it does NOT decide. The solver still owns correctness.

Model: DeepSeek-V4-Pro (independent family on purpose). See agents/CLAUDE.md.
The real implementation lives on branch `agents`.
"""

from __future__ import annotations

from typing import Any

from contracts import SolverResult


def critique(result: SolverResult, plan: Any) -> str:
    """
    Produce an adversarial risk critique of a chosen plan against the solver result.

    Args:
        result: Contract B from the solver.
        plan:   the plan under consideration (e.g. one ParetoPlan the human is eyeing).

    Returns:
        A critique string surfacing dissent and risk for the human to weigh.
    """
    raise NotImplementedError("Dev B implements critique() on branch `agents`.")
