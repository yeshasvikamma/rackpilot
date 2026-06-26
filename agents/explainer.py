"""
agents/explainer.py — Layer 3 explanation.  (STUB — Dev B)

Turns a SolverResult into a human-readable narrative for the capacity engineer:
what was placed and where, what the Pareto trade-offs mean, and — when infeasible —
what the IIS proof says in plain language. Explains; never decides.

Model: GPT-5.4, with Nemotron 3 Super as fallback. See agents/CLAUDE.md.
The real implementation lives on branch `agents`.
"""

from __future__ import annotations

from contracts import SolverResult


def explain(result: SolverResult) -> str:
    """
    Produce a plain-language explanation of a SolverResult for the human in the loop.

    Args:
        result: Contract B from the solver (mock or real).

    Returns:
        A human-facing narrative string. Describes the solver's output; it must not
        contradict or override it.
    """
    raise NotImplementedError("Dev B implements explain() on branch `agents`.")
