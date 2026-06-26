"""
solver/test_solver.py — the 3 solver gates.

These are written NOW as the definition of done for Track A (Dev A, branch `solver`).
They exercise the REAL solver in `solver.model.solve`, which on `main` raises
NotImplementedError — so all three are marked `xfail` (expected-fail) and `main`
stays green.

When Dev A's real solver makes a gate pass, REMOVE its `xfail` mark. When all three
xfail marks are gone and the tests pass, Track A is done.

Run:  pytest
"""

from __future__ import annotations

import pytest

from contracts import ChangeEvent, Constraint, ConstraintSpec, NewRack
from solver.model import solve


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _batch_8x40kw_spec() -> ConstraintSpec:
    """An 8-rack, 40kW-each, N+1 batch (Jalapeño-class) that only fits in Pod C."""
    racks = [
        NewRack(
            id=f"r_2{i:02d}",
            power_kw=40.0,
            u_height=42,
            weight_kg=1200.0,
            fabric_class="gpu-400g",
            cluster_id="jalapeno-1",
        )
        for i in range(1, 9)
    ]
    constraints = [
        Constraint(type="power_n1", hard=True, confidence=0.99, source="eaton-pdu"),
        Constraint(type="thermal_row_budget", hard=True, confidence=0.95, source="crac-telemetry"),
        Constraint(type="fabric_oversub", hard=True, confidence=0.90, source="netbox"),
        Constraint(type="space_contiguous_u", hard=True, confidence=0.98, source="dcim-floorplan"),
        Constraint(type="floor_weight", hard=False, confidence=0.60, source="structural-pdf-2019"),
    ]
    return ConstraintSpec(
        request_id="test-place-batch",
        mode="place_batch",
        new_racks=racks,
        objectives=["minimize_spend", "maximize_resilience", "maximize_future_headroom"],
        constraints=constraints,
    )


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
    result = solve(_batch_8x40kw_spec())

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
    """From a healthy facility, a feed derate -> exactly these racks newly violate."""
    spec = ConstraintSpec(
        request_id="test-break",
        mode="revalidate",
        constraints=[
            Constraint(type="power_n1", hard=True, confidence=0.99, source="eaton-pdu"),
        ],
        change_event=ChangeEvent(type="feed_derate", target="feed-A2", new_capacity_kw=300.0),
    )

    result = solve(spec)

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
    result = solve(_batch_8x40kw_spec())

    plans = result.pareto_plans
    assert len(plans) == 3, "expected a 3-plan Pareto frontier"

    for i, a in enumerate(plans):
        for j, b in enumerate(plans):
            if i != j:
                assert not _dominates(a, b), f"plan {i} dominates plan {j} — not a Pareto set"
