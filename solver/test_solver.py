"""
solver/test_solver.py — the 3 solver gates.

These are written as the definition of done for Track A (Dev A, branch `solver`).
They exercise the REAL solver in `solver.model.solve`, which on `main` raises
NotImplementedError — so all three are marked `xfail` (expected-fail) and `main`
stays green.

When Dev A's real solver makes a gate pass, REMOVE its `xfail` mark. When all three
xfail marks are gone and the tests pass, Track A is done.

VOCABULARY: reconciled to the verified seed (data/seed.py). The gates run against the
frozen, proven `SPEC_PLACE_BATCH` and `SPEC_FEED_DERATE` rather than a divergent inline
copy, so the solver has ONE canonical vocabulary to switch on:
    constraint types  — power_n_plus_1, thermal_zone, fabric_oversub, affinity, contiguity
    objectives        — min_spend, max_resilience, max_future_headroom
    derate target     — feed_B2 (140 -> 130 kW)
    batch             — jal_1..jal_8 @ 40kW / 4U, one affinity cluster (only fits Pod C)
    break racks       — r_113, r_118, r_124

Run:  pytest
"""

from __future__ import annotations

import pytest

from data.seed import SPEC_FEED_DERATE, SPEC_PLACE_BATCH
from solver.model import solve


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _dominates(a, b) -> bool:
    """
    True if Pareto plan `a` dominates `b`: at least as good on every objective and
    strictly better on at least one. Lower spend is better; higher resilience and
    higher future_headroom are better.
    """
    not_worse = (
        a.new_spend_usd <= b.new_spend_usd
        and a.resilience >= b.resilience
        and a.future_headroom >= b.future_headroom
    )
    strictly_better = (
        a.new_spend_usd < b.new_spend_usd
        or a.resilience > b.resilience
        or a.future_headroom > b.future_headroom
    )
    return not_worse and strictly_better


# ---------------------------------------------------------------------------
# Gate 1 — feasible batch placement
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="real solver not implemented on main; Dev A implements on branch `solver`",
    strict=False,
)
def test_place_batch():
    """8x 40kW N+1 batch -> feasible, all placements in Pod C, pods A & B violate, IIS non-empty."""
    result = solve(SPEC_PLACE_BATCH)

    assert result.status == "feasible"
    assert result.placements, "expected the batch to be placed"
    assert all(p.pod == "C" for p in result.placements), "the 40kW batch only fits in Pod C"

    violating_pods = {v.pod for v in result.violations}
    assert "A" in violating_pods, "Pod A must surface as violating"
    assert "B" in violating_pods, "Pod B must surface as violating"

    assert result.iis, "an IIS proof must be present"


# ---------------------------------------------------------------------------
# Gate 2 — the break moment
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="real solver not implemented on main; Dev A implements on branch `solver`",
    strict=False,
)
def test_break():
    """From a healthy facility, the feed_B2 derate -> exactly these racks newly violate."""
    result = solve(SPEC_FEED_DERATE)

    assert result.facility_diff is not None, "a revalidate must produce a facility_diff"
    assert result.facility_diff.newly_violating == ["r_113", "r_118", "r_124"]


# ---------------------------------------------------------------------------
# Gate 3 — Pareto frontier
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="real solver not implemented on main; Dev A implements on branch `solver`",
    strict=False,
)
def test_pareto():
    """pareto_plans has exactly 3 entries and none dominates another."""
    result = solve(SPEC_PLACE_BATCH)

    plans = result.pareto_plans
    assert len(plans) == 3, "expected a 3-plan Pareto frontier"

    for i, a in enumerate(plans):
        for j, b in enumerate(plans):
            if i != j:
                assert not _dominates(a, b), f"plan {i} dominates plan {j} — not a Pareto set"
