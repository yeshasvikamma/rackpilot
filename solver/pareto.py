"""
solver/pareto.py — the multi-objective Pareto frontier.  (Dev A, Terminal D)

Technique 4 of the solver (the CUT-FIRST one). Given the FEASIBLE place_batch spec,
produce three NON-DOMINATED plans that trade off the three objectives the engineer
cares about:

    min_spend          — dollars of new hardware
    max_resilience     — surplus redundancy: spare independent 400G paths beyond the
                         anti-affinity requirement, plus low blast radius (few racks
                         concentrated in any single enclosure / cooling zone)
    max_future_headroom— room for the NEXT cluster: spare 400G paths reusable later,
                         plus whole enclosures left fully free for a future contiguous
                         placement

NON-DOMINATION (the contract this module must honor): no returned plan may be
at-least-as-good as another on ALL three axes and strictly better on at least one
(spend lower = better; resilience / future_headroom higher = better).

HOW THE FRONTIER IS BUILT (against model.build_model's committed interface — this file
NEVER edits model.py):

  * Each plan is a real CP-SAT solve. We call build_model() and RE-OBJECTIVE it (CP-SAT's
    Minimize overwrites the prior objective) so a single model yields three genuinely
    different optima of the same batch in the one viable pod.
  * Spend is SOLVER-NATIVE. model.py's `new_switch_pair[pod]` is an IntVar(0, slots), so
    the MODEL decides how many 400G switch pairs to buy, and we read the count back from
    `purchased_pairs(solver)` (Dict[pod -> count]). We do NOT bolt on a hypothetical
    "what if we bought another pair" — the objective makes the model choose:
        - cheapest:      minimize pair purchases  -> the model buys the ONE pair
                         feasibility forces (free paths 0 + 1 pair*2 == the 2 required).
        - resilient /    reward buying a redundancy pair -> the model racks a SECOND pair
          future_proof:  into Pod C's free expansion slot (+2 independent paths). More
                         money genuinely buys redundancy + growth room.
    new_spend_usd is then sum(purchased_pairs counts) * NEW_400G_SWITCH_PAIR_USD.
  * Layout (resilience / future_headroom) stays legitimately layer-scored from the
    resulting placement, via a secondary objective term under the pair reward:
        - "spread":  minimize the max batch racks in any one enclosure -> low blast radius
          (high resilience), at the cost of touching every enclosure.
        - "compact": minimize the number of installed-empty enclosures touched -> leaves a
          whole enclosure FREE (high future headroom).

The result is three plans, each the UNIQUE optimum of one objective, so the set is a
guaranteed anti-chain:
    cheapest      — 1 pair (minimal spend), compact-packed layout.
    resilient     — 2 pairs + spread layout: most spare paths AND lowest blast radius.
    future_proof  — 2 pairs + compact layout: spare paths AND a free enclosure for next.

Everything is derived from the facility + the solves (no hardcoded pod ids, costs, or
distributions), so the logic is genuinely correct rather than special-cased to the demo.

PUBLIC INTERFACE:

    compute_pareto(spec, facility=None) -> list[dict]
        Returns plans shaped for SolverResult.pareto_plans:
        [{"label", "new_spend_usd", "resilience", "future_headroom"}, ...]
        Empty list if the batch is empty or infeasible (solve()/IIS own those cases).

Determinism is mandatory: same spec in -> same plans out (single worker, fixed seed,
lexicographic tie-break objectives).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from contracts import ConstraintSpec
from data.seed import (
    NEW_400G_SWITCH_PAIR_USD,
    PATHS_PER_SWITCH_PAIR,
    REQUIRED_400G_PATHS,
    build_facility,
    pod_free_400g_paths,
)
from solver.model import build_model

# Objective weight hierarchy (each tier dominates the sum of all tiers below it):
#   _PAIRS  — solver-native spend axis: buy / don't buy a redundancy pair (count <= 2)
#   _LAYOUT — the plan's layout penalty (max enclosure load, or empty enclosures used; <= ~8)
#   packing — deterministic tie-break (< ~1e4), keeps layouts reproducible run-to-run
_PAIRS = 1_000_000_000
_LAYOUT = 1_000_000


def _solver() -> cp_model.CpSolver:
    """Deterministic CP-SAT solver (single worker + fixed seed) — same settings as
    model._new_solver, kept local so this module depends only on the public interface."""
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = 15.0
    return solver


def _installed_empty_enclosures(facility: Dict[str, Any]) -> Set[Tuple[str, str]]:
    """(pod, enclosure) pairs that hold NO installed rack — i.e. enclosures that could
    be left fully free for a future contiguous cluster."""
    out: Set[Tuple[str, str]] = set()
    for pod_id, pod in facility["pods"].items():
        for enc_id in pod["enclosures"]:
            occupied = any(r["pod"] == pod_id and r["enclosure"] == enc_id
                           for r in facility["racks"].values())
            if not occupied:
                out.add((pod_id, enc_id))
    return out


def _packing_term(v) -> Any:
    """Deterministic lexicographic tie-break: prefer low enclosure index + low U so the
    layout (and thus the plans) reproduce run-to-run."""
    enc_index = {(p, e): i for p in v.pods for i, e in enumerate(v.enclosures[p])}
    return sum((enc_index[(p, e)] * 100 + u) * var
               for (rid, p, e, u), var in v.place.items())


def _total_pairs(v) -> Any:
    """The model's pair-purchase count across pods (a CP-SAT linear expr over the
    new_switch_pair IntVars) — this is the SOLVER-NATIVE spend axis."""
    return sum(v.new_switch_pair[p] for p in v.pods)


def _solve_placement(spec: ConstraintSpec, facility: Dict[str, Any],
                     emphasis: str) -> Optional[Dict[str, Any]]:
    """Build the feasible CP-SAT model, re-objective it for `emphasis`, solve, and return
    {pod, enc_counts, pairs} with `pairs` read from the SOLVER (purchased_pairs) — or None
    if the batch cannot be placed at all.

    emphasis="cheapest":     minimize pair purchases (-> 1 pair), compact-packed layout.
    emphasis="resilient":    reward a 2nd pair, then minimize the max racks in any one
                             enclosure (spread -> low blast radius).
    emphasis="future_proof": reward a 2nd pair, then minimize installed-empty enclosures
                             touched (compact -> leave a whole enclosure free).
    """
    model, v = build_model(spec, facility)
    total_pairs = _total_pairs(v)
    packing = _packing_term(v)

    if emphasis == "cheapest":
        # minimize spend (pairs); packing makes the resulting layout deterministic.
        model.Minimize(total_pairs * _PAIRS + packing)
    elif emphasis == "resilient":
        # reward redundancy pairs (maximize), then spread to cut blast radius.
        max_load = model.NewIntVar(0, len(v.racks), "pareto_max_enc_load")
        for p in v.pods:
            for enc in v.enclosures[p]:
                terms = [var for (rid, pp, e, u), var in v.place.items()
                         if pp == p and e == enc]
                if terms:
                    model.Add(max_load >= sum(terms))
        model.Minimize(max_load * _LAYOUT + packing - total_pairs * _PAIRS)
    elif emphasis == "future_proof":
        # reward redundancy pairs (maximize), then leave whole enclosures free (compact).
        empty = _installed_empty_enclosures(facility)
        used_empty: List[Any] = []
        for p in v.pods:
            for enc in v.enclosures[p]:
                if (p, enc) not in empty:
                    continue
                terms = [var for (rid, pp, e, u), var in v.place.items()
                         if pp == p and e == enc]
                if not terms:
                    continue
                b = model.NewBoolVar(f"pareto_used_empty_{p}_{enc}")
                for var in terms:
                    model.Add(b >= var)          # b = 1 if any batch rack lands here
                used_empty.append(b)
        model.Minimize(sum(used_empty) * _LAYOUT + packing - total_pairs * _PAIRS)
    else:  # pragma: no cover - guard against a typo'd emphasis
        raise ValueError(f"unknown emphasis {emphasis!r}")

    solver = _solver()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    pod = v.chosen_pod(solver)
    enc_counts: Dict[str, int] = {}
    for pl in v.placements_from(solver):
        enc_counts[pl.rack_enclosure] = enc_counts.get(pl.rack_enclosure, 0) + 1
    pairs = sum(v.purchased_pairs(solver).values())  # SOLVER-NATIVE pair count
    return {"pod": pod, "enc_counts": enc_counts, "pairs": pairs}


def _free_enclosure_capacity(facility: Dict[str, Any], pod: str,
                             enc_counts: Dict[str, int],
                             rack_u: int, rack_kg: float) -> int:
    """Future batch-class rack capacity of the installed-empty enclosures THIS plan
    leaves completely untouched (the contiguous room a future cluster could use)."""
    empty = {e for (p, e) in _installed_empty_enclosures(facility) if p == pod}
    total = 0
    for enc_id in empty:
        if enc_counts.get(enc_id, 0) != 0:
            continue  # this plan put racks here -> not free
        enc = facility["pods"][pod]["enclosures"][enc_id]
        by_u = enc["u_height"] // rack_u if rack_u else 0
        by_kg = int(enc["floor_tile_cap_kg"] // rack_kg) if rack_kg else by_u
        total += max(0, min(by_u, by_kg))
    return total


def _plan_metrics(facility: Dict[str, Any], pod: str, enc_counts: Dict[str, int],
                  pairs: int, rack_u: int, rack_kg: float) -> Tuple[float, float, float]:
    """Score one (placement, pairs) plan on the three objectives, all grounded in real
    facility quantities. `pairs` is the count the SOLVER bought. Returns
    (new_spend_usd, resilience, future_headroom)."""
    free_paths = pod_free_400g_paths(facility, pod)
    spare_paths = free_paths + pairs * PATHS_PER_SWITCH_PAIR - REQUIRED_400G_PATHS

    batch_total = sum(enc_counts.values())
    max_load = max(enc_counts.values()) if enc_counts else 0
    survive_worst_enclosure = batch_total - max_load  # racks left if the worst enc fails

    free_future = _free_enclosure_capacity(facility, pod, enc_counts, rack_u, rack_kg)

    new_spend_usd = float(pairs * NEW_400G_SWITCH_PAIR_USD)
    resilience = float(spare_paths + survive_worst_enclosure)
    future_headroom = float(spare_paths + free_future)
    return new_spend_usd, resilience, future_headroom


def compute_pareto(spec: ConstraintSpec,
                   facility: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Three non-dominated plans for a feasible place_batch spec, shaped for
    SolverResult.pareto_plans. Each plan is its own re-objectived CP-SAT solve, so its
    spend reflects the pairs the SOLVER actually bought. Empty list when there is nothing
    to place or the batch is infeasible (solve() and IIS own the infeasible story)."""
    if facility is None:
        facility = build_facility()
    if not spec.new_racks:
        return []

    rack_u = spec.new_racks[0].u_height
    rack_kg = spec.new_racks[0].weight_kg

    plans: List[Dict[str, Any]] = []
    for label in ("cheapest", "resilient", "future_proof"):
        layout = _solve_placement(spec, facility, label)
        if layout is None:
            return []  # infeasible — no frontier to report
        spend, resilience, future = _plan_metrics(
            facility, layout["pod"], layout["enc_counts"], layout["pairs"],
            rack_u, rack_kg)
        plans.append({
            "label": label,
            "new_spend_usd": spend,
            "resilience": resilience,
            "future_headroom": future,
        })
    return plans
