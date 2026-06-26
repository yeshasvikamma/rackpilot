"""
api/mock_solver.py — the UNBLOCK.  (WORKING — Dev B builds against this.)

This is a real, working `solve(spec) -> SolverResult` that returns a fully-populated,
schema-valid `SolverResult` (Contract B) with believable values. It lets Dev B build the
entire agents + api + ui half WITHOUT ever waiting for the real CP-SAT solver.

It does NOT solve anything — it returns a canned answer shaped like the real one:
a feasible batch placed in Pod C, pods A & B in violations, a 3-constraint IIS, a
3-plan Pareto frontier (none dominating another), proposed hardware, and a facility_diff
whose newly_violating is exactly ["r_113", "r_118", "r_124"].

The final integration is a one-line swap in api/main.py:
    from api.mock_solver import solve   ->   from solver.model import solve
"""

from __future__ import annotations

from contracts import (
    FacilityDiff,
    IIS,
    NewHardware,
    ParetoPlan,
    Placement,
    SolverResult,
    Violation,
)
from contracts import ConstraintSpec


def solve(spec: ConstraintSpec) -> SolverResult:
    """
    Return a hardcoded, schema-valid SolverResult that mirrors what the real solver
    will eventually produce. Echoes spec.request_id so callers can correlate.
    """
    return SolverResult(
        request_id=spec.request_id,
        status="feasible",
        # --- the 8x40kW batch lands in Pod C (the only pod with N+1 headroom) ---
        placements=[
            Placement(rack_id="r_201", pod="C", rack_enclosure="C-07", u_start=1),
            Placement(rack_id="r_202", pod="C", rack_enclosure="C-07", u_start=43),
            Placement(rack_id="r_203", pod="C", rack_enclosure="C-08", u_start=1),
            Placement(rack_id="r_204", pod="C", rack_enclosure="C-08", u_start=43),
            Placement(rack_id="r_205", pod="C", rack_enclosure="C-09", u_start=1),
            Placement(rack_id="r_206", pod="C", rack_enclosure="C-09", u_start=43),
            Placement(rack_id="r_207", pod="C", rack_enclosure="C-10", u_start=1),
            Placement(rack_id="r_208", pod="C", rack_enclosure="C-10", u_start=43),
        ],
        # --- a clean 3-point Pareto frontier; no plan dominates another ---
        # (lower spend is better; higher resilience and headroom are better)
        pareto_plans=[
            ParetoPlan(
                label="Lean — place now, no spend",
                new_spend_usd=0.0,
                resilience=0.72,
                future_headroom=0.15,
            ),
            ParetoPlan(
                label="Balanced — one busway + RDHx",
                new_spend_usd=85_000.0,
                resilience=0.88,
                future_headroom=0.40,
            ),
            ParetoPlan(
                label="Future-proof — new feed + cooling row",
                new_spend_usd=240_000.0,
                resilience=0.97,
                future_headroom=0.75,
            ),
        ],
        # --- pods A and B can't take this batch; surface why ---
        violations=[
            Violation(
                rack_id="r_201",
                pod="A",
                rule="power_n_plus_1",
                detail="Pod A feed pair A1/A2 cannot carry 8x40kW and survive one feed loss.",
            ),
            Violation(
                rack_id="r_201",
                pod="B",
                rule="thermal_row_budget",
                detail="Pod B row B-3 heat budget exceeded by 61kW with this batch.",
            ),
            Violation(
                rack_id="r_205",
                pod="B",
                rule="fabric_oversub",
                detail="Pod B spine oversubscription would hit 4.1:1, over the 3:1 cap.",
            ),
        ],
        # --- the IIS proof: three rules that cannot all hold at once ---
        iis=[
            IIS(
                constraints=["power_n_plus_1", "thermal_row_budget", "space_contiguous_u"],
                message=(
                    "No pod can satisfy all three at once for an 8x40kW N+1 batch: "
                    "the only contiguous-U space (Pod A) lacks N+1 power headroom, and "
                    "the only pod with both power and space (Pod B) blows its row heat budget."
                ),
            ),
        ],
        # --- what the solver would buy to lift a constraint ---
        new_hardware=[
            NewHardware(item="Busway tap-off, 250A 3-phase", pod="C", cost_usd=18_500.0),
            NewHardware(item="Rear-door heat exchanger (per enclosure)", pod="C", cost_usd=66_500.0),
        ],
        # --- the break moment's signature: exactly these racks newly violate ---
        facility_diff=FacilityDiff(
            version_from=7,
            version_to=8,
            newly_violating=["r_113", "r_118", "r_124"],
        ),
    )
