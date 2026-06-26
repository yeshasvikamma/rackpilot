"""
solver/iis.py — the Irreducible Infeasible Subset.  (Dev A, branch `solver`, Terminal B)

When the feasibility core (`solver/model.py`) reports that no placement exists, the
question Layer 3 negotiates over is *which rule bends*. The honest answer is the
**IIS**: the MINIMAL set of constraint *types* that together make the model
infeasible, such that relaxing any ONE of them makes it solvable again. Anything
larger is just "the list of constraints"; the IIS is the proof.

This module builds NOTHING of its own — it introspects the CP-SAT model that
`build_model()` already constructed, via its public `ModelVars.constraints_by_type`
handle (constraint references keyed by the spec's `type` string). It then runs
**deletion filtering**:

    iis := every relaxable constraint type present
    for each type t in iis:
        if (iis without t) is STILL infeasible:   # t was not pulling its weight
            drop t from iis
    # what remains is irreducible: dropping any member yields a feasible model

Deletion filtering provably returns a minimal infeasible subset: the working set
only shrinks and stays infeasible throughout (we drop t only when its removal keeps
infeasibility), and for any survivor t the set-minus-t was feasible at the moment we
kept it — so it is feasible for the (smaller) final set too. `solver/_smoke_iis.py`
re-proves this per constraint.

CANONICAL VOCABULARY (frozen — shared with the feasibility core's violations):

    power_n_plus_1 · thermal_zone · fabric_oversub · affinity · contiguity

The structural background — each rack placed once, no U-cell overlap, floor weight —
is NOT in this vocabulary by design: it is the *demand* and the *physics*, the fixed
backdrop the negotiable rules collide against, never itself a lever. So the IIS is
always reported in the five canonical names above (plus, optionally, a resource
token such as ``feed_B2_capacity`` when a single feed is the binder).

PUBLIC INTERFACE:

    compute_iis(spec, facility=None, pin_pod=None) -> list[dict]
        [] if the model is feasible; otherwise a one-element list shaped for
        SolverResult.iis: [{"constraints": [<canonical types>], "message": <plain>}].

    model_is_infeasible(spec, facility, relax=frozenset(), pin_pod=None) -> bool
        The single deletion-filter primitive (also used by the smoke to prove
        minimality): rebuild the model, neutralize every constraint whose type is in
        `relax`, optionally pin the cluster to one pod, and report infeasibility.

No LLM, no network. Deterministic: same spec in -> same IIS out.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Iterable, List, Optional

from ortools.sat.python import cp_model

from contracts import ConstraintSpec
from data.seed import build_facility, pod_power_n_plus_1_headroom_kw
from solver.model import build_model

# The frozen IIS vocabulary, in the canonical reporting order (power -> ... -> soft).
CANONICAL_TYPES = ("power_n_plus_1", "thermal_zone", "fabric_oversub", "affinity", "contiguity")

# Older scaffold vocabulary -> canonical, so the IIS speaks one language regardless of
# which `type` strings the incoming spec happened to carry. Unknown types map to
# themselves; structural types (space/weight) are intentionally absent — they are
# background, never reported as a negotiable IIS member.
_CANONICAL_ALIAS: Dict[str, str] = {
    "power_n1": "power_n_plus_1",
    "thermal_row_budget": "thermal_zone",
}


def _canonical(constraint_type: str) -> str:
    return _CANONICAL_ALIAS.get(constraint_type, constraint_type)


# ---------------------------------------------------------------------------
# The deletion-filter primitive
# ---------------------------------------------------------------------------

def _neutralize(constraint: Any) -> None:
    """Turn one CP-SAT constraint into a no-op (an empty ConstraintProto is always
    true), so the rest of the model is solved AS IF that constraint were relaxed.
    Every constraint `build_model()` records is linear, but we defensively clear
    whichever constraint oneof is actually set."""
    proto = constraint.proto
    for kind in ("linear", "bool_and", "bool_or", "at_most_one", "exactly_one", "bool_xor"):
        if getattr(proto, f"has_{kind}")():
            getattr(proto, f"clear_{kind}")()
            return


def _new_solver() -> cp_model.CpSolver:
    """A deterministic solver (single worker, fixed seed) — same settings as the
    feasibility core, so an IIS probe sees exactly the core's notion of feasibility."""
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = 15.0
    return solver


def model_is_infeasible(spec: ConstraintSpec,
                        facility: Optional[Dict[str, Any]] = None,
                        relax: Iterable[str] = frozenset(),
                        pin_pod: Optional[str] = None) -> bool:
    """Rebuild the model for `spec`/`facility`, relax (neutralize) every constraint
    whose canonical type is in `relax`, optionally pin the whole cluster into
    `pin_pod`, and return True iff the result is infeasible.

    Rebuilding fresh each call is deliberate: neutralizing a constraint is destructive,
    so every probe starts from a clean model. This is the one primitive the deletion
    filter (and the smoke's minimality proof) is built on."""
    if facility is None:
        facility = build_facility()
    relax_set = {_canonical(t) for t in relax}

    model, v = build_model(spec, facility)
    if pin_pod is not None:
        # Operational pin: "the engineer requires this cluster in pod X." Part of the
        # fixed problem statement (background), never a relaxable IIS member.
        model.Add(v.pod_sel[pin_pod] == 1)

    for ctype, constraints in v.constraints_by_type.items():
        if _canonical(ctype) in relax_set:
            for constraint in constraints:
                _neutralize(constraint)

    status = _new_solver().Solve(model)
    return status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)


# ---------------------------------------------------------------------------
# IIS
# ---------------------------------------------------------------------------

def _candidate_types(spec: ConstraintSpec, facility: Dict[str, Any]) -> List[str]:
    """The relaxable canonical types actually present (non-empty) in the model,
    in canonical order. Empty groups (e.g. soft `contiguity`, which the core does not
    hard-enforce) are excluded — they can never be part of an irreducible *hard* core."""
    _, v = build_model(spec, facility)
    present = {_canonical(t) for t, cs in v.constraints_by_type.items() if cs}
    return [t for t in CANONICAL_TYPES if t in present]


def compute_iis(spec: ConstraintSpec,
                facility: Optional[Dict[str, Any]] = None,
                pin_pod: Optional[str] = None) -> List[Dict[str, Any]]:
    """Compute the irreducible infeasible subset for `spec` over `facility`.

    Returns [] when the model is feasible (there is nothing to prove). When it is
    infeasible, returns a single-element list shaped for `SolverResult.iis`:

        [{"constraints": [<canonical type strings>], "message": "<plain explanation>"}]

    The constraint list is genuinely MINIMAL: every member is necessary (relaxing it
    alone restores feasibility) and the whole set is sufficient (keeping all of them is
    infeasible). Deterministic.
    """
    if facility is None:
        facility = build_facility()

    candidates = _candidate_types(spec, facility)

    # Feasible as posed -> no IIS to report.
    if not model_is_infeasible(spec, facility, relax=frozenset(), pin_pod=pin_pod):
        return []

    # Deletion filtering over the canonical candidates. `iis` is the set of types we
    # still ENFORCE; relaxing the complement. A type is dropped only if the model
    # stays infeasible WITHOUT it (it was not contributing to the conflict).
    iis: List[str] = list(candidates)
    for t in candidates:
        trial = [x for x in iis if x != t]
        relax = set(candidates) - set(trial)          # everything not enforced in the trial
        if model_is_infeasible(spec, facility, relax=relax, pin_pod=pin_pod):
            iis = trial                                # t is not necessary -> drop it
        # else: removing t made it feasible -> t is necessary -> keep it

    iis.sort(key=CANONICAL_TYPES.index)
    message = _explain(iis, spec, facility, pin_pod)
    return [{"constraints": iis, "message": message}]


def _explain(iis_types: List[str], spec: ConstraintSpec,
             facility: Dict[str, Any], pin_pod: Optional[str]) -> str:
    """A plain-English proof sentence: what collides, the binding numbers, and the
    levers. Names the binding pod / headroom for the power case as the optional
    resource detail the contract allows."""
    has = set(iis_types)
    n = len(spec.new_racks)
    demand_kw = sum(r.power_kw for r in spec.new_racks)
    headrooms = {p: pod_power_n_plus_1_headroom_kw(facility, p) for p in facility["pods"]}
    best_pod = max(headrooms, key=headrooms.get) if headrooms else None
    best_kw = headrooms.get(best_pod, 0.0)

    # Build the clauses in canonical order so the sentence is deterministic.
    clauses: List[str] = []
    for t in CANONICAL_TYPES:
        if t not in has:
            continue
        if t == "power_n_plus_1":
            clauses.append(
                f"under N+1 redundancy no single pod can supply the {demand_kw:.0f}kW the "
                f"cluster draws (the roomiest, pod {best_pod}, offers only {best_kw:.0f}kW of "
                f"surviving-feed headroom)"
            )
        elif t == "thermal_zone":
            clauses.append("the per-zone cooling budget cannot absorb the cluster's heat")
        elif t == "fabric_oversub":
            clauses.append("the fabric cannot supply the required independent redundant 400G paths")
        elif t == "affinity":
            where = f"pod {pin_pod}" if pin_pod else "a single pod"
            clauses.append(f"the affinity rule keeps all {n} cluster racks in {where}")
        elif t == "contiguity":
            clauses.append("the cluster's contiguous-placement preference cannot be met")

    if not clauses:
        return (
            "The placement is infeasible, but the binding constraints are structural "
            "(physical space / floor-weight) rather than any negotiable rule — there is no "
            "constraint in the {power_n_plus_1, thermal_zone, fabric_oversub, affinity, "
            "contiguity} vocabulary whose removal would help."
        )

    body = "; and ".join(clauses)
    levers = ", ".join(iis_types)
    return (
        f"No feasible placement exists: {body}. This subset is irreducible — relaxing any "
        f"one of [{levers}] makes the problem solvable, while keeping all of them does not."
    )
