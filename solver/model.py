"""
solver/model.py — the deterministic CP-SAT feasibility core.  (Dev A, branch `solver`)

This is Layer 2, the SPINE. OR-Tools CP-SAT, no LLM, no network. It is the only
place in RackPilot where placement decisions are made. It consumes a reconciled
`ConstraintSpec` (Contract A) and returns a `SolverResult` (Contract B), honoring
all four scarce resource classes AT ONCE:

    power (N+1 redundancy)  ·  thermal (cooling budget)  ·  fabric (400G paths +
    oversubscription)  ·  space (contiguous rack-units + floor weight)

plus the cluster AFFINITY rule (all of one cluster's racks in a single pod).

For the canonical demo spec (`SPEC_PLACE_BATCH`: 8x40kW, N+1, one affinity cluster)
the facility numbers are engineered so the batch is feasible ONLY in Pod C, with
Pod A blocked on power N+1 and Pod B blocked on fabric (it cannot supply two
independent redundant 400G paths -> an anti-affinity / blast-radius violation).
The solver does not "make" Pod C win; it discovers it.

PUBLIC INTERFACE (Terminals B/C/D build against this — keep it stable):

    build_model(spec, facility) -> (model, vars)
        Constructs the CP-SAT model and a `ModelVars` handle exposing the decision
        variables AND the constraint references keyed by ConstraintSpec `type` string
        (so IIS can introspect by type and Pareto can swap objectives).

    solve(spec, facility=None) -> SolverResult
        Full feasibility solve. Default facility = data.seed.build_facility().

    check_power_n_plus_1 / check_thermal / check_fabric / check_space_weight
        The four resource checks as separately-callable, named functions — each a
        pure-Python per-pod feasibility test, independently verifiable.

Determinism is mandatory: same spec in -> same SolverResult out (single worker,
fixed seed, lexicographic tie-break objective).

`iis` and `pareto_plans` are intentionally left empty here — Terminal B fills IIS,
Terminal D fills Pareto, both against this interface. The result is always
schema-valid Contract B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from contracts import (
    ConstraintSpec,
    NewHardware,
    NewRack,
    Placement,
    SolverResult,
    Violation,
)
from data.seed import (
    NEW_400G_SWITCH_PAIR_USD,
    PATHS_PER_SWITCH_PAIR,
    REQUIRED_400G_PATHS,
    build_facility,
    pod_fabric_expansion_slots,
    pod_free_400g_paths,
    pod_power_n_plus_1_headroom_kw,
    pod_thermal_headroom_kw,
)

# ---------------------------------------------------------------------------
# Vocabulary: map a ConstraintSpec.type string to its resource CLASS.
#
# Two vocabularies exist in the repo: the reconciled seed vocabulary used by
# SPEC_PLACE_BATCH (power_n_plus_1, thermal_zone, fabric_oversub, affinity,
# contiguity) and the older scaffold vocabulary in test_solver.py (power_n1,
# thermal_row_budget, space_contiguous_u, floor_weight). build_model() keys its
# constraint handles by whatever `type` strings the spec actually carries, so it
# works for either — IIS then reports the real spec type names.
# ---------------------------------------------------------------------------

POWER = "power"
THERMAL = "thermal"
FABRIC = "fabric"
SPACE = "space"
WEIGHT = "weight"
AFFINITY = "affinity"
CONTIGUITY = "contiguity"  # soft: cluster-adjacency preference, not enforced here

_RESOURCE_OF_TYPE: Dict[str, str] = {
    "power_n_plus_1": POWER,
    "power_n1": POWER,
    "thermal_zone": THERMAL,
    "thermal_row_budget": THERMAL,
    "fabric_oversub": FABRIC,
    "affinity": AFFINITY,
    "contiguity": CONTIGUITY,
    "space_contiguous_u": SPACE,
    "floor_weight": WEIGHT,
}


def resource_class_of(constraint_type: str) -> str:
    """Resource class for a ConstraintSpec.type (unknown types fall back to themselves)."""
    return _RESOURCE_OF_TYPE.get(constraint_type, constraint_type)


def _kw(x: float) -> int:
    """Seed quantities are integral kW/kg; round defensively for CP-SAT (ints only)."""
    return int(round(x))


# ===========================================================================
# The four resource checks — pure-Python, per-pod, independently callable.
#
# These mirror, at the pod level, exactly what the CP-SAT model enforces, and are
# the single source for the "why is this pod infeasible" reasons reported in
# SolverResult.violations. They reuse data/seed.py's helpers — the N+1 / thermal /
# fabric math is never reimplemented here.
# ===========================================================================

@dataclass
class ResourceCheck:
    """Result of one per-pod resource feasibility test."""

    resource: str           # canonical class (POWER / THERMAL / FABRIC / SPACE)
    ok: bool
    rule: str               # diagnostic label used for Violation.rule
    detail: str
    new_pairs_needed: int = 0   # fabric: 400G switch pairs to buy to satisfy paths


def check_power_n_plus_1(facility: Dict[str, Any], pod_id: str,
                         racks: List[NewRack]) -> ResourceCheck:
    """N+1 power: the pod's spare (per feed pair, surviving one feed) must cover the
    new load. Reuses seed.pod_power_n_plus_1_headroom_kw (sum of per-pair slack,
    each pair's slack = min(cap_a, cap_b) - current load)."""
    need = sum(r.power_kw for r in racks)
    headroom = pod_power_n_plus_1_headroom_kw(facility, pod_id)
    ok = need <= headroom
    detail = (
        f"Pod {pod_id} N+1 power headroom {headroom:.0f}kW "
        f"{'>=' if ok else '<'} {need:.0f}kW required "
        f"({len(racks)} racks); under N+1 each feed pair must survive losing one feed."
    )
    return ResourceCheck(POWER, ok, "power_n_plus_1", detail)


def check_thermal(facility: Dict[str, Any], pod_id: str,
                  racks: List[NewRack]) -> ResourceCheck:
    """Pod-zone cooling (aggregate BY DESIGN — see build_model): placed heat must fit
    the pod's total spare cooling (sum over rows of cooling - installed heat). Reuses
    seed.pod_thermal_headroom_kw."""
    need = sum(r.power_kw for r in racks)  # heat ~= electrical load for these racks
    headroom = pod_thermal_headroom_kw(facility, pod_id)
    ok = need <= headroom
    detail = (
        f"Pod {pod_id} cooling headroom {headroom:.0f}kW "
        f"{'>=' if ok else '<'} {need:.0f}kW of new heat."
    )
    return ResourceCheck(THERMAL, ok, "thermal_zone", detail)


def check_fabric(facility: Dict[str, Any], pod_id: str,
                 racks: List[NewRack]) -> ResourceCheck:
    """Fabric: the cluster needs REQUIRED_400G_PATHS independent redundant 400G paths.
    A pod supplies free paths now + (switch pairs it can rack) * PATHS_PER_SWITCH_PAIR.
    Too few -> the cluster's redundant members would share a path: an anti-affinity /
    blast-radius violation. Also checks the static oversubscription cap."""
    free = pod_free_400g_paths(facility, pod_id)
    slots = pod_fabric_expansion_slots(facility, pod_id)
    fabric = facility["pods"][pod_id]["fabric"]
    cap, ratio = fabric["oversub_cap"], fabric["oversub_ratio"]

    reachable = free + slots * PATHS_PER_SWITCH_PAIR
    short = max(0, REQUIRED_400G_PATHS - free)
    pairs_needed = (short + PATHS_PER_SWITCH_PAIR - 1) // PATHS_PER_SWITCH_PAIR  # ceil

    paths_ok = reachable >= REQUIRED_400G_PATHS
    oversub_ok = ratio <= cap
    ok = paths_ok and oversub_ok

    # The canonical fabric constraint type is "fabric_oversub" (the frozen vocabulary).
    # Keep the rule field on that ONE name for BOTH fabric failure modes — path
    # shortfall and oversubscription — and let the detail string carry the specific
    # reason. This guarantees IIS (Terminal B) and these violation reasons never use
    # two different names for the same fabric constraint.
    rule = "fabric_oversub"
    if not paths_ok:
        detail = (
            f"blast-radius / anti-affinity: Pod {pod_id} has only {reachable} reachable "
            f"400G path(s) ({free} free + {slots} expansion slot(s)) < "
            f"{REQUIRED_400G_PATHS} required, so the cluster's redundant members would "
            f"share a path."
        )
    elif not oversub_ok:
        detail = (f"Pod {pod_id} oversubscription {ratio:.1f}:1 exceeds the "
                  f"{cap:.1f}:1 cap.")
    else:
        detail = (
            f"Pod {pod_id} reaches {REQUIRED_400G_PATHS} independent 400G paths "
            f"({free} free + {pairs_needed} new pair(s)); oversub {ratio:.1f}:1 "
            f"<= {cap:.1f}:1 cap."
        )
    return ResourceCheck(FABRIC, ok, rule, detail, new_pairs_needed=pairs_needed)


def check_space_weight(facility: Dict[str, Any], pod_id: str,
                       racks: List[NewRack]) -> ResourceCheck:
    """Space + weight: can the pod's enclosures hold the racks as contiguous-U blocks
    without exceeding any floor-tile weight cap? Analytic capacity estimate (the CP-SAT
    model is the real decider); used only to surface a reason, never to place."""
    installed = [r for r in facility["racks"].values() if r["pod"] == pod_id]
    capacity = 0
    for enc_id, enc in facility["pods"][pod_id]["enclosures"].items():
        used_u = sum(r["u_height"] for r in installed if r["enclosure"] == enc_id)
        used_kg = sum(r["weight_kg"] for r in installed if r["enclosure"] == enc_id)
        free_u = enc["u_height"] - used_u
        free_kg = enc["floor_tile_cap_kg"] - used_kg
        # how many of THESE racks (assume the batch is uniform) fit this enclosure
        per_rack_u = racks[0].u_height if racks else 1
        per_rack_kg = racks[0].weight_kg if racks else 0.0
        by_u = free_u // per_rack_u if per_rack_u else 0
        by_kg = int(free_kg // per_rack_kg) if per_rack_kg else by_u
        capacity += max(0, min(by_u, by_kg))
    ok = capacity >= len(racks)
    detail = (
        f"Pod {pod_id} can host ~{capacity} of these racks across its enclosures "
        f"(contiguous-U + floor-weight); needs {len(racks)}."
    )
    return ResourceCheck(SPACE, ok, "space_contiguous_u", detail)


_CHECKS = (check_power_n_plus_1, check_thermal, check_fabric, check_space_weight)


def pod_binding_reason(facility: Dict[str, Any], pod_id: str,
                       racks: List[NewRack]) -> Optional[ResourceCheck]:
    """First failing resource check for a pod (the binding reason it can't host the
    batch), or None if the pod can host it. Checks run in resource order
    power -> thermal -> fabric -> space so the report is deterministic."""
    for check in _CHECKS:
        result = check(facility, pod_id, racks)
        if not result.ok:
            return result
    return None


# ===========================================================================
# Decision model
# ===========================================================================

@dataclass
class ModelVars:
    """Handle to the CP-SAT decision variables and constraint references.

    Exposed so Terminal B (IIS) can introspect constraints by ConstraintSpec type,
    and Terminal D (Pareto) can re-objective the same model.
    """

    pods: List[str]
    racks: List[NewRack]
    enclosures: Dict[str, List[str]]                      # pod -> [enclosure ids]
    # decision variables
    place: Dict[Tuple[str, str, str, int], Any]           # (rack,pod,enc,u_start) -> BoolVar
    pod_sel: Dict[str, Any]                                # pod -> BoolVar (cluster hosted here)
    new_switch_pair: Dict[str, Any]                        # pod -> BoolVar (buy a 400G pair)
    # constraint references
    constraints_by_class: Dict[str, List[Any]] = field(default_factory=dict)
    constraints_by_type: Dict[str, List[Any]] = field(default_factory=dict)
    pair_cost: float = NEW_400G_SWITCH_PAIR_USD

    # -- solution extraction helpers (used by solve() and by C/D) --------------
    def chosen_pod(self, solver: cp_model.CpSolver) -> Optional[str]:
        for p in self.pods:
            if solver.Value(self.pod_sel[p]):
                return p
        return None

    def placements_from(self, solver: cp_model.CpSolver) -> List[Placement]:
        out: List[Placement] = []
        for (rack_id, pod, enc, u_start), var in self.place.items():
            if solver.Value(var):
                out.append(Placement(rack_id=rack_id, pod=pod,
                                     rack_enclosure=enc, u_start=u_start))
        out.sort(key=lambda pl: (pl.pod, pl.rack_enclosure, pl.u_start))
        return out

    def purchased_pairs(self, solver: cp_model.CpSolver) -> List[str]:
        return [p for p in self.pods if solver.Value(self.new_switch_pair[p])]


def _aligned_or_all_starts(enc_u: int, rack_u: int) -> List[int]:
    """Every valid integer u_start where a rack_u-tall rack fits in an enc_u enclosure."""
    return list(range(1, enc_u - rack_u + 2)) if rack_u <= enc_u else []


def _occupied_cells(facility: Dict[str, Any], pod_id: str, enc_id: str) -> set:
    """U cells already taken by installed racks in this enclosure."""
    cells: set = set()
    for r in facility["racks"].values():
        if r["pod"] == pod_id and r["enclosure"] == enc_id:
            cells.update(range(r["u_start"], r["u_start"] + r["u_height"]))
    return cells


def build_model(spec: ConstraintSpec,
                facility: Dict[str, Any]) -> Tuple[cp_model.CpModel, ModelVars]:
    """Build the CP-SAT feasibility model for a place_batch spec over the whole
    facility, returning (model, vars). All four resource classes plus affinity are
    enforced simultaneously. Constraint handles are recorded by resource class and
    re-keyed by the spec's own constraint `type` strings (for IIS / Pareto)."""
    model = cp_model.CpModel()
    racks = list(spec.new_racks)
    pods = list(facility["pods"].keys())

    enclosures: Dict[str, List[str]] = {
        p: list(facility["pods"][p]["enclosures"].keys()) for p in pods
    }

    by_class: Dict[str, List[Any]] = {}

    def record(ctr, cls: str):
        by_class.setdefault(cls, []).append(ctr)
        return ctr

    # -- decision variables ----------------------------------------------------
    place: Dict[Tuple[str, str, str, int], Any] = {}
    for r in racks:
        for p in pods:
            for enc_id, enc in facility["pods"][p]["enclosures"].items():
                occupied = _occupied_cells(facility, p, enc_id)
                for u in _aligned_or_all_starts(enc["u_height"], r.u_height):
                    cells = range(u, u + r.u_height)
                    if any(c in occupied for c in cells):
                        continue  # would overlap an installed rack
                    place[(r.id, p, enc_id, u)] = model.NewBoolVar(
                        f"place_{r.id}_{p}_{enc_id}_{u}")

    pod_sel = {p: model.NewBoolVar(f"pod_sel_{p}") for p in pods}
    new_switch_pair = {p: model.NewBoolVar(f"new_switch_pair_{p}") for p in pods}

    # -- AFFINITY: the whole cluster lands in exactly one pod ------------------
    record(model.Add(sum(pod_sel.values()) == 1), AFFINITY)
    for r in racks:
        # each rack placed exactly once (structural)
        record(model.Add(sum(v for (rid, *_), v in place.items() if rid == r.id) == 1),
                SPACE)
    for (rid, p, enc, u), v in place.items():
        # a rack may only sit in the selected pod
        record(model.Add(v <= pod_sel[p]), AFFINITY)

    # -- POWER (N+1) + THERMAL: new load / heat in a pod <= its headroom -------
    # THERMAL IS A POD-ZONE AGGREGATE BY DESIGN: heat is constrained against the pod's
    # total spare cooling (sum over rows of cooling - installed heat). This is exact for
    # an affinity-bound cluster (the whole batch lands in one pod) and matches the
    # zone-level thermal scorecard. True per-row enforcement would need an
    # enclosure->row map, which the seed does not provide (e.g. Pod C's C-03/C-04 have
    # no installed racks to infer a row from) — so we deliberately stay at pod zone.
    rack_by_id = {r.id: r for r in racks}
    for p in pods:
        terms_power = []
        terms_heat = []
        for (rid, pp, enc, u), v in place.items():
            if pp != p:
                continue
            terms_power.append(_kw(rack_by_id[rid].power_kw) * v)
            terms_heat.append(_kw(rack_by_id[rid].power_kw) * v)  # heat ~= load
        if terms_power:
            record(model.Add(sum(terms_power)
                             <= _kw(pod_power_n_plus_1_headroom_kw(facility, p))), POWER)
            record(model.Add(sum(terms_heat)
                             <= _kw(pod_thermal_headroom_kw(facility, p))), THERMAL)

    # -- FABRIC: independent 400G paths + remediation + oversub ----------------
    for p in pods:
        free = pod_free_400g_paths(facility, p)
        slots = pod_fabric_expansion_slots(facility, p)
        fabric = facility["pods"][p]["fabric"]
        # may only buy a pair in the selected pod, and only as many as there are slots
        record(model.Add(new_switch_pair[p] <= slots), FABRIC)
        record(model.Add(new_switch_pair[p] <= pod_sel[p]), FABRIC)
        # if hosted here, free + bought*paths_per_pair must reach the required paths
        record(model.Add(free + new_switch_pair[p] * PATHS_PER_SWITCH_PAIR
                         >= REQUIRED_400G_PATHS * pod_sel[p]), FABRIC)
        # static oversubscription cap: can't host here if already over
        if fabric["oversub_ratio"] > fabric["oversub_cap"]:
            record(model.Add(pod_sel[p] == 0), FABRIC)

    # -- SPACE + WEIGHT: no overlap per U cell, floor weight per enclosure ------
    for p in pods:
        for enc_id, enc in facility["pods"][p]["enclosures"].items():
            occupied = _occupied_cells(facility, p, enc_id)
            installed_kg = sum(r["weight_kg"] for r in facility["racks"].values()
                               if r["pod"] == p and r["enclosure"] == enc_id)
            # no two racks (new, or new vs installed) share a U cell
            for k in range(1, enc["u_height"] + 1):
                covering = [v for (rid, pp, e, u), v in place.items()
                            if pp == p and e == enc_id and u <= k < u + rack_by_id[rid].u_height]
                if k in occupied:
                    for v in covering:
                        record(model.Add(v == 0), SPACE)
                elif covering:
                    record(model.Add(sum(covering) <= 1), SPACE)
            # floor-tile weight cap
            weight_terms = [_kw(rack_by_id[rid].weight_kg) * v
                            for (rid, pp, e, u), v in place.items()
                            if pp == p and e == enc_id]
            if weight_terms:
                record(model.Add(sum(weight_terms)
                                 <= _kw(enc["floor_tile_cap_kg"] - installed_kg)), WEIGHT)

    # -- OBJECTIVE: minimize spend, then a tiny deterministic packing tie-break -
    # pair_cost (240k) dwarfs the packing term (< ~10k), so spend strictly dominates;
    # the tie-break just makes placement reproducible run-to-run.
    enc_index = {(p, e): i for p in pods for i, e in enumerate(enclosures[p])}
    spend = sum(_kw(NEW_400G_SWITCH_PAIR_USD) * new_switch_pair[p] for p in pods)
    packing = sum((enc_index[(p, e)] * 100 + u) * v
                  for (rid, p, e, u), v in place.items())
    model.Minimize(spend + packing)

    # -- re-key constraint handles by the spec's own constraint type strings ----
    by_type: Dict[str, List[Any]] = {}
    for c in spec.constraints:
        cls = resource_class_of(c.type)
        by_type.setdefault(c.type, [])
        by_type[c.type].extend(by_class.get(cls, []))

    vars_ = ModelVars(
        pods=pods,
        racks=racks,
        enclosures=enclosures,
        place=place,
        pod_sel=pod_sel,
        new_switch_pair=new_switch_pair,
        constraints_by_class=by_class,
        constraints_by_type=by_type,
    )
    return model, vars_


# ===========================================================================
# solve()
# ===========================================================================

def _new_solver() -> cp_model.CpSolver:
    """A deterministic CP-SAT solver: single worker + fixed seed -> reproducible."""
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = 15.0
    return solver


def _violations_for(facility: Dict[str, Any], racks: List[NewRack],
                    skip_pod: Optional[str]) -> List[Violation]:
    """One Violation per pod that cannot host the batch (skipping the chosen pod),
    carrying that pod's binding reason."""
    rep = racks[0].id if racks else ""
    out: List[Violation] = []
    for pod_id in sorted(facility["pods"].keys()):
        if pod_id == skip_pod:
            continue
        reason = pod_binding_reason(facility, pod_id, racks)
        if reason is not None:
            out.append(Violation(rack_id=rep, pod=pod_id,
                                 rule=reason.rule, detail=reason.detail))
    return out


def solve(spec: ConstraintSpec,
          facility: Optional[Dict[str, Any]] = None) -> SolverResult:
    """Solve all four resource classes simultaneously for `spec` and return Contract B.

    Feasible -> status="feasible", placements in the one viable pod, new_hardware for
    any 400G pair bought, and violations explaining every pod that could NOT host the
    batch. Infeasible -> status="infeasible" with violations for all pods.

    `iis` and `pareto_plans` are left empty (Terminals B and D own those). Deterministic.
    """
    if facility is None:
        facility = build_facility()

    racks = list(spec.new_racks)
    model, v = build_model(spec, facility)
    solver = _new_solver()
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen = v.chosen_pod(solver) if racks else None
        placements = v.placements_from(solver)
        new_hardware = [
            NewHardware(item="400G redundant switch pair", pod=p,
                        cost_usd=v.pair_cost)
            for p in v.purchased_pairs(solver)
        ]
        violations = _violations_for(facility, racks, skip_pod=chosen)
        return SolverResult(
            request_id=spec.request_id,
            status="feasible",
            placements=placements,
            new_hardware=new_hardware,
            violations=violations,
            pareto_plans=[],
            iis=[],
        )

    # No pod can host the batch — report every pod's binding reason. (Terminal B
    # adds the minimal IIS proof on top of this.)
    violations = _violations_for(facility, racks, skip_pod=None)
    return SolverResult(
        request_id=spec.request_id,
        status="infeasible",
        placements=[],
        new_hardware=[],
        violations=violations,
        pareto_plans=[],
        iis=[],
    )
