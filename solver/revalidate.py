"""
solver/revalidate.py — incremental re-solve on change (the break moment). (Dev A, branch `solver`)

When the infrastructure changes (a power feed derate, a cooling unit dropping, a
higher-power chip), RackPilot must re-evaluate the facility and report what NEWLY
breaks. This module owns that path for Layer 2: `revalidate(spec, facility=None)`.

Pure Python on top of the DigitalTwin + CP-SAT. No LLM, no network. Deterministic.

HOW THE DEMO "break moment" WORKS (the pure feed_derate revalidate)
-------------------------------------------------------------------
1. Wrap the facility as version T0 in a `DigitalTwin` (immutable history).
2. Apply the `ChangeEvent` (feed_B2: 140 -> 130 kW) -> a NEW version T1. T0 is left
   byte-for-byte unchanged — nothing mutates the prior state.
3. Ask the twin to `diff(T0, T1)`. THE TWIN IS THE SOURCE OF TRUTH for the diff: it
   delegates N+1 compliance to `data/seed.py`'s helpers and returns
   `newly_violating` already in canonical board order. We never reimplement the N+1
   math here and never recompute the diff independently.
4. Emit a Contract-B `SolverResult` whose `facility_diff` is the twin's diff verbatim
   (`version_from` / `version_to` stay INTS), with one `Violation` per newly-violating
   rack (rule = the canonical "power_n_plus_1") explaining the breach under the
   derated feed.

For the demo derate this yields `newly_violating == ["r_113", "r_118", "r_124"]` — the
three racks sharing the (feed_B1, feed_B2) pair at a 135 kW load that 130 kW can no
longer survive losing one feed.

INCREMENTAL WARM-START (when a change actually re-places hardware)
-----------------------------------------------------------------
The pure feed_derate revalidate re-places NOTHING — the twin-diff violation set IS the
answer, so no CP-SAT placement re-solve is needed. But when a change carries new racks
to (re)place, `revalidate` finds the MINIMAL repair by WARM-STARTING the post-change
model from the prior solution (CP-SAT solution hints via `warm_start_resolve`) rather
than cold-planning from scratch. The demo path (`spec.new_racks == []`) never enters
this branch, so the break moment stays a clean, deterministic twin diff.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from contracts import (
    ConstraintSpec,
    FacilityDiff,
    NewHardware,
    Placement,
    SolverResult,
    Violation,
)
from data.seed import feed_caps_full, feed_pair_load_kw
from data.twin import DigitalTwin

# model.py's committed public interface — the feasibility core we warm-start from.
from solver.model import build_model, solve

#: The frozen, canonical rule name for an N+1 power breach (matches the seed
#: vocabulary `power_n_plus_1` used across ConstraintSpec / violations).
POWER_N_PLUS_1_RULE = "power_n_plus_1"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def revalidate(spec: ConstraintSpec,
               facility: Optional[Dict[str, Any]] = None) -> SolverResult:
    """
    Re-evaluate the facility after a `ChangeEvent` (carried on `spec.change_event`)
    and return Contract B with the `facility_diff` populated.

    The change is applied THROUGH the DigitalTwin immutably (the prior version is never
    mutated); the twin's own `diff` — which delegates N+1 to seed.py and emits
    `newly_violating` in canonical order — is the single source of truth for what broke.

    For the demo's feed_B2 derate (140 -> 130 kW) this yields
        facility_diff.newly_violating == ["r_113", "r_118", "r_124"]
    with `version_from` / `version_to` as INTS, and one Violation per rack.

    Args:
        spec:     Contract A in mode "revalidate", carrying the change_event.
        facility: the internal facility dict to start from (version T0). Default
                  None -> the seed facility (`data.seed.build_facility()` via the twin).

    Returns:
        Contract B. `placements` / `iis` / `pareto_plans` are empty on the pure
        revalidate path; a change that re-places hardware fills `placements` /
        `new_hardware` via an incremental warm-start.
    """
    change = spec.change_event
    if change is None:
        raise ValueError("revalidate requires spec.change_event (the infrastructure change)")

    # 1-2. Immutable apply: T0 = facility (or seed), T1 = post-change. ---------
    twin = DigitalTwin(facility)
    v_from = twin.latest_version            # "T0"
    v_to = twin.apply_change(change)        # "T1" — prior version untouched

    # 3. The twin owns the diff (canonical order, seed-delegated N+1 math). ----
    diff = twin.diff(v_from, v_to)
    newly_violating: List[str] = list(diff["newly_violating"])

    # version_from / version_to are INTS straight from the twin — never stringify.
    facility_diff = FacilityDiff(
        version_from=diff["version_from"],
        version_to=diff["version_to"],
        newly_violating=newly_violating,
    )

    # 4. One canonical N+1 violation per newly-violating rack, with the breach
    #    detail read off the post-change (derated) state. ----------------------
    state_to = twin.get_state(v_to)
    violations = _n_plus_1_violations(state_to, newly_violating, change.target)

    # A change that tips racks into N+1 violation leaves the facility infeasible.
    status = "infeasible" if newly_violating else "feasible"

    # 5. Incremental repair ONLY when the change re-places hardware. The pure
    #    feed_derate revalidate (no new racks) skips this entirely. ------------
    placements: List[Placement] = []
    new_hardware: List[NewHardware] = []
    if spec.new_racks:
        repair = warm_start_resolve(spec, twin.get_state(v_from), state_to)
        placements = repair.placements
        new_hardware = repair.new_hardware
        if repair.status == "infeasible":
            status = "infeasible"

    return SolverResult(
        request_id=spec.request_id,
        status=status,
        placements=placements,
        new_hardware=new_hardware,
        violations=violations,
        pareto_plans=[],
        iis=[],
        facility_diff=facility_diff,
    )


# ---------------------------------------------------------------------------
# Violation reporting (descriptive only — the twin already DECIDED which racks)
# ---------------------------------------------------------------------------

def _n_plus_1_violations(state: Dict[str, Any], rack_ids: List[str],
                         derate_target: str) -> List[Violation]:
    """One `Violation` per newly-violating rack, in the order the twin reported them.

    The set of racks is the twin's decision; here we only READ the post-change load
    and surviving feed capacity (via seed helpers) to phrase WHY each rack breaches
    N+1 under the derate. We do not re-decide compliance.
    """
    caps = feed_caps_full(state)            # derated capacities of THIS version
    out: List[Violation] = []
    for rack_id in rack_ids:
        rack = state["racks"][rack_id]
        a, b = tuple(rack["feed_pair"])
        load = feed_pair_load_kw(state, (a, b))
        surviving = min(caps[a], caps[b])   # one feed of the pair down -> the weaker survivor
        detail = (
            f"feed pair ({a},{b}) load {load:.0f}kW > {surviving:.0f}kW surviving "
            f"capacity after {derate_target} derate "
            f"(N+1 = survive losing one feed: surviving = min({a}={caps[a]:.0f}kW, "
            f"{b}={caps[b]:.0f}kW))."
        )
        out.append(Violation(
            rack_id=rack_id,
            pod=rack["pod"],
            rule=POWER_N_PLUS_1_RULE,
            detail=detail,
        ))
    return out


# ---------------------------------------------------------------------------
# Incremental warm-start re-solve (used when a change re-places hardware)
# ---------------------------------------------------------------------------

def warm_start_resolve(spec: ConstraintSpec,
                       facility_before: Dict[str, Any],
                       facility_after: Dict[str, Any]) -> SolverResult:
    """Re-solve placement on the POST-change facility, warm-started from the prior
    solution so CP-SAT searches for the MINIMAL repair near the previous placement
    instead of cold-planning from scratch.

    The prior solution is the feasibility solve of `facility_before`; its placements
    are fed back as CP-SAT solution HINTS on the `facility_after` model. Hints are
    advisory — CP-SAT keeps the ones still satisfiable and repairs only what the
    change broke. Deterministic (single worker, fixed seed).
    """
    prior = solve(spec, facility_before)                 # the warm-start seed
    model, vars_ = build_model(spec, facility_after)     # public interface from model.py
    _apply_solution_hints(model, vars_, prior.placements)

    solver = _deterministic_solver()
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolverResult(
            request_id=spec.request_id,
            status="feasible",
            placements=vars_.placements_from(solver),
            new_hardware=[
                NewHardware(item="400G redundant switch pair", pod=p, cost_usd=vars_.pair_cost)
                for p in vars_.purchased_pairs(solver)
            ],
            violations=[],
            pareto_plans=[],
            iis=[],
        )

    return SolverResult(
        request_id=spec.request_id,
        status="infeasible",
        placements=[],
        new_hardware=[],
        violations=[],
        pareto_plans=[],
        iis=[],
    )


def _apply_solution_hints(model: cp_model.CpModel, vars_: Any,
                          prior_placements: List[Placement]) -> None:
    """Seed the model with the prior solution as CP-SAT hints (warm start)."""
    chosen = {
        (p.rack_id, p.pod, p.rack_enclosure, p.u_start) for p in prior_placements
    }
    for key, var in vars_.place.items():
        model.AddHint(var, 1 if key in chosen else 0)


def _deterministic_solver() -> cp_model.CpSolver:
    """A reproducible CP-SAT solver: single worker + fixed seed -> same answer every run."""
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = 15.0
    return solver
