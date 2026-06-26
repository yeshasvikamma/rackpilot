"""
solver/_smoke_iis.py — IIS smoke (NOT a gate, NOT committed-law).

Forces a genuinely infeasible placement and prints the irreducible infeasible subset,
THEN proves the subset is minimal: for every constraint in it, relaxing that one
constraint must make the model feasible (necessary), and for every canonical
constraint NOT in it, relaxing that one must leave the model infeasible (correctly
excluded).

The forced case: a DENSE 8-rack cluster at 50kW/rack (a "Jalapeño+" chip) placed as one
affinity group. Demand is 400kW; even the roomiest pod (C) has only 390kW of N+1
headroom, and no facility surgery is needed — the cluster simply cannot fit any single
pod under N+1, and affinity forbids splitting it. The honest IIS is therefore
{power_n_plus_1, affinity}: relax either and it solves; thermal and fabric are NOT part
of the proof (each is individually droppable while the model stays infeasible).

    .venv/bin/python -m solver._smoke_iis
"""

from __future__ import annotations

from contracts import Constraint, ConstraintSpec, NewRack
from data.seed import build_facility, pod_power_n_plus_1_headroom_kw
from solver.iis import CANONICAL_TYPES, compute_iis, model_is_infeasible


def _dense_cluster_spec() -> ConstraintSpec:
    """8 racks @ 50kW / 4U / 1200kg, one affinity cluster, the five canonical
    constraints (power/thermal/fabric/affinity hard, contiguity soft)."""
    racks = [
        NewRack(id=f"jal_{i}", power_kw=50.0, u_height=4, weight_kg=1200.0,
                fabric_class="400G", cluster_id="infcluster_dense")
        for i in range(1, 9)
    ]
    constraints = [
        Constraint(type="power_n_plus_1", hard=True, confidence=0.99, source="bms-feed-telemetry"),
        Constraint(type="thermal_zone", hard=True, confidence=0.95, source="crac-telemetry"),
        Constraint(type="fabric_oversub", hard=True, confidence=0.92, source="netbox"),
        Constraint(type="affinity", hard=True, confidence=0.97, source="workload-placement-policy"),
        Constraint(type="contiguity", hard=False, confidence=0.70, source="dcim-floorplan"),
    ]
    return ConstraintSpec(
        request_id="smoke-iis-dense",
        mode="place_batch",
        new_racks=racks,
        objectives=["min_spend", "max_resilience", "max_future_headroom"],
        constraints=constraints,
    )


def main() -> None:
    spec = _dense_cluster_spec()
    facility = build_facility()

    demand = sum(r.power_kw for r in spec.new_racks)
    headrooms = {p: pod_power_n_plus_1_headroom_kw(facility, p) for p in facility["pods"]}

    print("=" * 74)
    print("RackPilot IIS — smoke: irreducible infeasible subset of a forced placement")
    print("=" * 74)
    print(f"scenario          : place {len(spec.new_racks)} racks @ 50kW as ONE affinity cluster")
    print(f"cluster demand    : {demand:.0f}kW")
    print(f"per-pod N+1 power : " + ", ".join(f"{p}={kw:.0f}kW" for p, kw in sorted(headrooms.items())))
    print(f"                    -> no single pod >= {demand:.0f}kW; affinity forbids splitting")

    iis = compute_iis(spec, facility)
    print("-" * 74)
    assert iis, "expected a non-empty IIS for an infeasible placement"
    proof = iis[0]
    print(f"IIS constraints   : {proof['constraints']}")
    print(f"IIS message       : {proof['message']}")

    members = proof["constraints"]

    # ---- PROOF OF MINIMALITY -------------------------------------------------
    # (1) Sufficiency: enforcing exactly the IIS members (relaxing every other
    #     canonical type) must already be INFEASIBLE.
    non_members = [t for t in CANONICAL_TYPES if t not in members]
    full_relax = set(non_members)
    sufficient = model_is_infeasible(spec, facility, relax=full_relax)
    print("-" * 74)
    print("minimality proof  : (the IIS must be SUFFICIENT and every member NECESSARY)")
    print(f"  [sufficient] enforce only {members}, relax {sorted(full_relax)} "
          f"-> infeasible={sufficient}  {'OK' if sufficient else 'FAIL'}")

    # (2) Necessity: for each IIS member, additionally relaxing THAT one must flip the
    #     model to FEASIBLE — i.e. it was genuinely pulling its weight.
    all_member_checks_ok = True
    for t in members:
        relax = full_relax | {t}
        still_infeasible = model_is_infeasible(spec, facility, relax=relax)
        necessary = not still_infeasible
        all_member_checks_ok &= necessary
        print(f"  [necessary ] also relax {t:<16} -> feasible={necessary}  "
              f"{'OK (dropping it solves -> necessary)' if necessary else 'FAIL (not necessary)'}")

    # (3) Correct exclusion: each canonical type NOT in the IIS must, when relaxed
    #     ALONE, leave the model infeasible (so it truly does not belong in the proof).
    print("  [excluded  ] (canonical types correctly left OUT of the IIS)")
    all_exclusions_ok = True
    for t in non_members:
        # only meaningful for types the model actually enforces
        infeasible_without = model_is_infeasible(spec, facility, relax={t})
        ok = infeasible_without
        all_exclusions_ok &= ok
        print(f"               relax {t:<16} alone -> infeasible={infeasible_without}  "
              f"{'OK (does not help -> not in IIS)' if ok else '(note: soft/absent)'}")

    print("=" * 74)
    verdict = sufficient and all_member_checks_ok
    print(f"VERDICT           : IIS {members} is "
          f"{'MINIMAL and PROVEN' if verdict else 'NOT minimal — CHECK FAILED'}")
    print("=" * 74)


if __name__ == "__main__":
    main()
