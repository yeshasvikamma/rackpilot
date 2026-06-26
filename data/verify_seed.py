"""
data/verify_seed.py — Phase 1 GATE 1 (seed).  (Dev A, branch `solver`)

Proves, with NO solver — just arithmetic over the seed facility dict — that the two
demo narratives are TRUE BY CONSTRUCTION:

  1. PLACE_BATCH (8x40kW = 320kW, N+1, one affinity cluster):
       Pod A INFEASIBLE on power   (N+1 headroom << 320kW)
       Pod B INFEASIBLE on fabric  (exactly 1 free redundant 400G path, no expansion)
       Pod C FEASIBLE              (power+thermal+space+weight >= 320; 0 free 400G
                                    paths -> needs 1 NEW switch pair)

  2. FEED_DERATE (feed_B2 140 -> 130 kW):
       exactly {r_113, r_118, r_124} flip compliant -> violation; nothing else moves.

Run:  python data/verify_seed.py
Exits 0 if every check passes, nonzero (1) if any check fails.
"""

from __future__ import annotations

import os
import sys

# Make repo root importable whether run as `python data/verify_seed.py` or `-m`.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.seed import (  # noqa: E402
    REQUIRED_400G_PATHS,
    SPEC_FEED_DERATE,
    SPEC_PLACE_BATCH,
    batch_required_kw,
    batch_required_u,
    batch_required_weight_kg,
    build_facility,
    feed_caps_full,
    pod_fabric_expansion_slots,
    pod_free_400g_paths,
    pod_free_u,
    pod_power_n_plus_1_headroom_kw,
    pod_reachable_400g_paths,
    pod_thermal_headroom_kw,
    pod_weight_headroom_kg,
    rack_is_n_plus_1_compliant,
)

# ---------------------------------------------------------------------------
# tiny check harness — prints PASS/FAIL, accumulates failures, exits nonzero
# ---------------------------------------------------------------------------

_FAILURES: list = []


def check(cond: bool, label: str) -> None:
    tag = "PASS" if cond else "FAIL"
    print(f"   [{tag}] {label}")
    if not cond:
        _FAILURES.append(label)


def hr(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def main() -> int:
    facility = build_facility()
    req_kw = batch_required_kw()
    req_u = batch_required_u()
    req_wt = batch_required_weight_kg()

    hr("BATCH REQUIREMENT (spec_place_batch)")
    racks = SPEC_PLACE_BATCH.new_racks
    print(f"   request_id      : {SPEC_PLACE_BATCH.request_id}  mode={SPEC_PLACE_BATCH.mode}")
    print(f"   new racks       : {len(racks)} x {racks[0].power_kw:.0f}kW / "
          f"{racks[0].u_height}U  ({racks[0].id}..{racks[-1].id})")
    print(f"   cluster/fabric  : {racks[0].cluster_id} / {racks[0].fabric_class}")
    print(f"   objectives      : {SPEC_PLACE_BATCH.objectives}")
    print(f"   constraints     : "
          + ", ".join(f"{c.type}({'hard' if c.hard else 'soft'})"
                      for c in SPEC_PLACE_BATCH.constraints))
    print(f"   => required     : power {req_kw:.0f}kW (N+1) | space {req_u}U | "
          f"weight {req_wt:.0f}kg | {REQUIRED_400G_PATHS} redundant 400G paths")
    check(len(racks) == 8 and all(r.power_kw == 40.0 for r in racks),
          "batch is 8 racks @ 40kW")
    check([r.id for r in racks] == [f"jal_{i}" for i in range(1, 9)],
          "batch ids are jal_1..jal_8")

    # ---------------------------------------------------------------- Pod A
    hr("POD A  — must be INFEASIBLE on POWER (N+1)")
    a_pwr = pod_power_n_plus_1_headroom_kw(facility, "A")
    a_paths = pod_free_400g_paths(facility, "A")
    print(f"   N+1 power headroom : {a_pwr:.0f} kW   (required {req_kw:.0f} kW)")
    print(f"   free 400G paths    : {a_paths}   (fabric is NOT A's blocker)")
    check(a_pwr < req_kw,
          f"Pod A N+1 power headroom {a_pwr:.0f}kW < required {req_kw:.0f}kW")

    # ---------------------------------------------------------------- Pod B
    hr("POD B  — must be INFEASIBLE on FABRIC (anti-affinity / blast-radius)")
    b_paths = pod_free_400g_paths(facility, "B")
    b_slots = pod_fabric_expansion_slots(facility, "B")
    b_reach = pod_reachable_400g_paths(facility, "B")
    b_pwr = pod_power_n_plus_1_headroom_kw(facility, "B")
    print(f"   free 400G paths     : {b_paths}   (required {REQUIRED_400G_PATHS})")
    print(f"   expansion slots     : {b_slots}   (new switch pairs it can rack)")
    print(f"   max reachable paths : {b_reach}   = free + slots*{2}")
    print(f"   N+1 power headroom  : {b_pwr:.0f} kW  (B HAS the power; fabric is the wall)")
    check(b_paths == 1, "Pod B free redundant 400G paths == 1")
    check(b_slots == 0, "Pod B has 0 fabric expansion slots (cannot remediate)")
    check(b_reach < REQUIRED_400G_PATHS,
          f"Pod B can reach only {b_reach} < {REQUIRED_400G_PATHS} required paths -> INFEASIBLE")
    check(b_pwr >= req_kw, f"Pod B power headroom {b_pwr:.0f}kW >= {req_kw:.0f}kW (not B's blocker)")

    # ---------------------------------------------------------------- Pod C
    hr("POD C  — must be FEASIBLE, needs 1 NEW 400G switch pair")
    c_pwr = pod_power_n_plus_1_headroom_kw(facility, "C")
    c_thr = pod_thermal_headroom_kw(facility, "C")
    c_u = pod_free_u(facility, "C")
    c_wt = pod_weight_headroom_kg(facility, "C")
    c_paths = pod_free_400g_paths(facility, "C")
    c_slots = pod_fabric_expansion_slots(facility, "C")
    c_reach = pod_reachable_400g_paths(facility, "C")
    cost = facility["fabric_catalog"]["new_400g_switch_pair_usd"]
    print(f"   N+1 power headroom : {c_pwr:.0f} kW   (required {req_kw:.0f} kW)")
    print(f"   thermal headroom   : {c_thr:.0f} kW   (required {req_kw:.0f} kW)")
    print(f"   free space         : {c_u} U     (required {req_u} U)")
    print(f"   weight headroom    : {c_wt:.0f} kg (required {req_wt:.0f} kg)")
    print(f"   free 400G paths    : {c_paths}   -> needs 1 NEW switch pair (+{2} paths)")
    print(f"   reachable w/ buy   : {c_reach}   (>= {REQUIRED_400G_PATHS} required)")
    print(f"   remediation cost   : ${cost:,.0f}  (1x 400G switch pair)")
    check(c_pwr >= req_kw, f"Pod C power headroom {c_pwr:.0f}kW >= {req_kw:.0f}kW")
    check(c_thr >= req_kw, f"Pod C thermal headroom {c_thr:.0f}kW >= {req_kw:.0f}kW")
    check(c_u >= req_u, f"Pod C free space {c_u}U >= {req_u}U")
    check(c_wt >= req_wt, f"Pod C weight headroom {c_wt:.0f}kg >= {req_wt:.0f}kg")
    check(c_paths == 0, "Pod C free redundant 400G paths == 0 (needs a new pair)")
    check(c_reach >= REQUIRED_400G_PATHS,
          f"Pod C reaches {c_reach} >= {REQUIRED_400G_PATHS} paths by buying 1 pair -> FEASIBLE")

    # ------------------------------------------------ FEED DERATE (the break)
    hr("FEED DERATE  — feed_B2: exactly {r_113, r_118, r_124} flip")
    ce = SPEC_FEED_DERATE.change_event
    target = ce.target
    derated_kw = ce.new_capacity_kw
    caps_full = feed_caps_full(facility)
    caps_derated = dict(caps_full)
    caps_derated[target] = derated_kw
    print(f"   change_event    : {ce.type}  target={target}  "
          f"{caps_full[target]:.0f}kW -> {derated_kw:.0f}kW")
    print()
    print(f"   {'rack':<8} {'pod':<4} {'feed_pair':<22} {'pair_kW':>8} "
          f"{'@full':>7} {'@derate':>8}  flip")
    print("   " + "-" * 66)

    flipped = []
    for rid in sorted(facility["racks"]):
        r = facility["racks"][rid]
        pair = tuple(r["feed_pair"])
        pair_str = f"{pair[0]},{pair[1]}"
        load = sum(x["power_kw"] for x in facility["racks"].values()
                   if tuple(x["feed_pair"]) == pair)
        ok_full = rack_is_n_plus_1_compliant(facility, rid, caps_full)
        ok_der = rack_is_n_plus_1_compliant(facility, rid, caps_derated)
        flip = ok_full and not ok_der
        if flip:
            flipped.append(rid)
        s_full = "ok" if ok_full else "VIOL"
        s_der = "ok" if ok_der else "VIOL"
        mark = "  <== FLIP" if flip else ""
        print(f"   {rid:<8} {r['pod']:<4} {pair_str:<22} {load:>8.0f} "
              f"{s_full:>7} {s_der:>8}{mark}")

    expected = {"r_113", "r_118", "r_124"}
    print()
    print(f"   flipped compliant->violation : {sorted(flipped)}")
    print(f"   expected                     : {sorted(expected)}")
    check(set(flipped) == expected,
          "exactly {r_113, r_118, r_124} flip compliant->violation, nothing else")

    # healthy baseline sanity: everyone compliant before the derate
    all_healthy = all(rack_is_n_plus_1_compliant(facility, rid, caps_full)
                      for rid in facility["racks"])
    check(all_healthy, "healthy baseline: every installed rack is N+1 compliant at full feeds")

    # ----------------------------------------------------------------- verdict
    hr("VERDICT")
    if _FAILURES:
        print(f"   {len(_FAILURES)} CHECK(S) FAILED:")
        for f in _FAILURES:
            print(f"     - {f}")
        print("\n   GATE 1 (seed): FAILED")
        return 1
    print("   ALL CHECKS PASSED")
    print("   GATE 1 (seed): GREEN — narratives are true by construction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
