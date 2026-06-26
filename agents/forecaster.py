"""
agents/forecaster.py — capacity forecasting.  (STUB — Dev B)

  *** CUT-FIRST ***
  Per the scope-cut order in the root CLAUDE.md, the forecaster is the FIRST thing
  to drop if time runs short. Build it last; do not let it block anything.

Looks ahead: given the facility and the current placements, narrates when the next
resource runs out (power headroom, thermal budget, fabric ports, floor space) so the
engineer can plan procurement. Advisory narrative only — it does not decide.

Model: Nemotron 3 Super. See agents/CLAUDE.md.
The real implementation lives on branch `agents`.
"""

from __future__ import annotations

from typing import Any

from contracts import SolverResult


def forecast(result: SolverResult, horizon: Any = None) -> str:
    """
    Produce a forward-looking capacity narrative.

    Args:
        result:  Contract B from the solver.
        horizon: how far ahead to forecast (agents decide the concrete shape).

    Returns:
        A human-facing forecast string. CUT THIS FIRST if time runs short.
    """
    raise NotImplementedError("Dev B implements forecast() on branch `agents`.")
