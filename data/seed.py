"""
data/seed.py — the seed facility and demo scenarios.  (Dev A, branch `solver`)

Builds RackPilot's ground-truth facility: pods, rows, rack enclosures, power feeds
(with their N+1 pairing), per-row cooling/heat budgets, network fabric ports +
oversubscription, and the racks already installed. Also produces the two canonical
demo ConstraintSpecs (the 8x40kW batch placement, and the feed_B2 derate "break").

Pure Python. No LLM. No network. Deterministic: same call -> same facility.

THE GOLDEN RULE OF PHASE 1
--------------------------
The numbers below are engineered so the demo narratives are TRUE BY CONSTRUCTION —
not by any solver trick. The solver is never allowed to "make" Pod C win; the facility
is built so Pod C is genuinely the only feasible pod, and derating `feed_B2` genuinely
tips exactly {r_113, r_118, r_124} into N+1 violation and nothing else. `verify_seed.py`
proves both narratives by inspecting THIS data alone (no solver).

The two narratives this data forces:

  1. PLACE_BATCH — 8 racks @ 40kW, N+1 required, one affinity cluster (320kW total):
       * Pod A: INFEASIBLE on power. Its feeds, under N+1 (one feed of a pair down),
                have only 70kW of headroom << 320kW.
       * Pod B: INFEASIBLE on fabric. Only ONE free redundant 400G path remains and the
                pod has no switch-pair expansion slots, so the cluster (which needs 2
                independent redundant paths) can't be placed without blast-radius /
                anti-affinity violation, and can't be remediated.
       * Pod C: FEASIBLE. Has power + thermal + space + weight headroom >= 320kW, but
                has 0 free redundant 400G paths — so it requires 1 NEW 400G switch pair
                (a known $ remediation cost; a pair yields 2 paths == the requirement).

  2. FEED_DERATE — derate feed_B2 from 140kW to 130kW:
       * r_113 / r_118 / r_124 share the (feed_B1, feed_B2) N+1 pair at a combined load
         of 135kW. At full capacity 135 <= min(140,140) -> N+1 compliant. After the
         derate 135 > min(140,130)=130 -> all three violate. No other rack sits on a
         pair containing feed_B2, so NO OTHER rack changes state.

Frozen IDs (law): pods A/B/C; new racks jal_1..jal_8; break racks r_113/r_118/r_124;
target feed feed_B2.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from contracts import ChangeEvent, Constraint, ConstraintSpec, NewRack

# ---------------------------------------------------------------------------
# Demo / policy constants (single source of truth for the narratives)
# ---------------------------------------------------------------------------

BATCH_SIZE: int = 8
BATCH_RACK_KW: float = 40.0           # OpenAI Jalapeno-class density
BATCH_RACK_U: int = 4
BATCH_RACK_WEIGHT_KG: float = 1200.0
BATCH_FABRIC_CLASS: str = "400G"
BATCH_CLUSTER_ID: str = "infcluster_A"

#: A 400G "redundant path" = one switch of a redundant switch pair; spreading a
#: cluster's redundant members across 2 INDEPENDENT paths is what survives one path
#: failing. The Jalapeno cluster needs 2 such paths to satisfy fabric anti-affinity.
REQUIRED_400G_PATHS: int = 2
#: Buying one new 400G switch pair adds this many independent redundant paths.
PATHS_PER_SWITCH_PAIR: int = 2
#: Known remediation cost of the one new 400G switch pair Pod C needs.
NEW_400G_SWITCH_PAIR_USD: float = 240_000.0

#: feed_B2's healthy capacity and the value the demo derates it to.
FEED_B2_FULL_KW: float = 140.0
FEED_B2_DERATED_KW: float = 130.0


# ---------------------------------------------------------------------------
# build_facility() — the version-0 ground truth
# ---------------------------------------------------------------------------

def build_facility() -> Dict[str, Any]:
    """
    Build and return the healthy baseline facility as a plain, inspectable dict.

    Schema (internal to Dev A — it never crosses the contract boundary):

        facility = {
          "name": str,
          "racks": { rack_id -> {pod, power_kw, heat_kw, u_height, u_start,
                                 weight_kg, enclosure, row, feed_pair: (a, b)} },
          "pods": { pod_id -> {
              "feeds":      { feed_id -> {capacity_kw, partner} },
              "feed_pairs": [ (feed_a, feed_b), ... ],
              "rows":       { row_id -> {cooling_kw} },
              "enclosures": { enc_id -> {u_height, floor_tile_cap_kg} },
              "fabric": {
                 "switch_pairs": { pair_id -> {paths: [ {in_use_by}, {in_use_by} ]} },
                 "free_switch_pair_slots": int,   # how many NEW pairs can be racked
                 "oversub_ratio": float,
                 "oversub_cap": float,
              },
          }},
          "fabric_catalog": {"new_400g_switch_pair_usd", "paths_per_pair"},
          "policy": {"n_plus_1_required", "required_400g_paths_for_cluster"},
        }

    Same call -> identical facility, every time.
    """
    facility: Dict[str, Any] = {
        "name": "RackPilot synthetic DC (3 pods)",
        "racks": {},
        "pods": {},
        "fabric_catalog": {
            "new_400g_switch_pair_usd": NEW_400G_SWITCH_PAIR_USD,
            "paths_per_pair": PATHS_PER_SWITCH_PAIR,
        },
        "policy": {
            "n_plus_1_required": True,
            "required_400g_paths_for_cluster": REQUIRED_400G_PATHS,
        },
    }

    # -- POWER FEEDS (paired for N+1) -------------------------------------
    # Pod A: two pairs at 150kW each, deliberately loaded so N+1 headroom is tiny.
    # Pod B: the maxed (feed_B1,feed_B2) pair at 140kW + two roomy 220kW pairs.
    # Pod C: two roomy 250kW pairs.
    facility["pods"]["A"] = _pod_skeleton(
        feeds={
            "feed_A1": (150.0, "feed_A2"), "feed_A2": (150.0, "feed_A1"),
            "feed_A3": (150.0, "feed_A4"), "feed_A4": (150.0, "feed_A3"),
        },
        feed_pairs=[("feed_A1", "feed_A2"), ("feed_A3", "feed_A4")],
        rows={"A-r1": 300.0, "A-r2": 300.0},
        enclosures={"A-01": (42, 5000.0), "A-02": (42, 5000.0)},
        fabric=_fabric(
            # Pod A fabric is FINE (free paths = 2); A's only failure is power.
            switch_pairs={
                "A-spine-1": ["existing-svc", "existing-svc"],
                "A-spine-2": [None, None],
            },
            free_switch_pair_slots=1,
            oversub_ratio=3.0,
            oversub_cap=4.0,
        ),
    )
    facility["pods"]["B"] = _pod_skeleton(
        feeds={
            "feed_B1": (FEED_B2_FULL_KW, "feed_B2"), "feed_B2": (FEED_B2_FULL_KW, "feed_B1"),
            "feed_B3": (220.0, "feed_B4"), "feed_B4": (220.0, "feed_B3"),
            "feed_B5": (220.0, "feed_B6"), "feed_B6": (220.0, "feed_B5"),
        },
        feed_pairs=[("feed_B1", "feed_B2"), ("feed_B3", "feed_B4"), ("feed_B5", "feed_B6")],
        rows={"B-r1": 200.0, "B-r2": 250.0, "B-r3": 250.0},
        enclosures={"B-01": (42, 5000.0), "B-02": (42, 5000.0), "B-03": (42, 5000.0)},
        fabric=_fabric(
            # Pod B fabric is the blocker: exactly ONE free path, and NO room to add
            # a new switch pair (0 expansion slots) -> can't reach the 2 required.
            switch_pairs={
                "B-spine-1": ["tenant-db", "tenant-db"],
                "B-spine-2": ["tenant-ml", None],
            },
            free_switch_pair_slots=0,
            oversub_ratio=3.2,
            oversub_cap=4.0,
        ),
    )
    facility["pods"]["C"] = _pod_skeleton(
        feeds={
            "feed_C1": (250.0, "feed_C2"), "feed_C2": (250.0, "feed_C1"),
            "feed_C3": (250.0, "feed_C4"), "feed_C4": (250.0, "feed_C3"),
        },
        feed_pairs=[("feed_C1", "feed_C2"), ("feed_C3", "feed_C4")],
        rows={"C-r1": 250.0, "C-r2": 250.0, "C-r3": 200.0},
        enclosures={
            "C-01": (42, 5000.0), "C-02": (42, 5000.0),
            "C-03": (42, 5000.0), "C-04": (42, 5000.0),
        },
        fabric=_fabric(
            # Pod C fabric: 0 free paths, but 2 expansion slots -> buy 1 new pair
            # (+2 paths) == the requirement. Feasible WITH a known $ cost.
            switch_pairs={
                "C-spine-1": ["tenant-web", "tenant-web"],
                "C-spine-2": ["tenant-cache", "tenant-batch"],
            },
            free_switch_pair_slots=2,
            oversub_ratio=2.5,
            oversub_cap=4.0,
        ),
    )

    # -- INSTALLED RACKS --------------------------------------------------
    # (rack_id, pod, power_kw, weight_kg, enclosure, u_start, row, feed_pair)
    installed: List[Tuple[str, str, float, float, str, int, str, Tuple[str, str]]] = [
        # Pod A — feeds nearly maxed under N+1 (headroom 70kW total), lots of free U.
        ("r_101", "A", 60.0, 1000.0, "A-01", 1, "A-r1", ("feed_A1", "feed_A2")),
        ("r_102", "A", 60.0, 1000.0, "A-01", 5, "A-r1", ("feed_A1", "feed_A2")),
        ("r_103", "A", 55.0, 1000.0, "A-02", 1, "A-r2", ("feed_A3", "feed_A4")),
        ("r_104", "A", 55.0, 1000.0, "A-02", 5, "A-r2", ("feed_A3", "feed_A4")),
        # Pod B — the break trio on (feed_B1,feed_B2): 3x45 = 135kW, just under 140.
        ("r_113", "B", 45.0, 1000.0, "B-01", 1, "B-r1", ("feed_B1", "feed_B2")),
        ("r_118", "B", 45.0, 1000.0, "B-01", 5, "B-r1", ("feed_B1", "feed_B2")),
        ("r_124", "B", 45.0, 1000.0, "B-01", 9, "B-r1", ("feed_B1", "feed_B2")),
        # Pod B — other racks on roomy pairs (give B its 320kW power headroom).
        ("r_110", "B", 50.0, 1000.0, "B-02", 1, "B-r2", ("feed_B3", "feed_B4")),
        ("r_111", "B", 40.0, 1000.0, "B-03", 1, "B-r3", ("feed_B5", "feed_B6")),
        # Pod C — light load, big headroom on every axis.
        ("r_130", "C", 60.0, 1000.0, "C-01", 1, "C-r1", ("feed_C1", "feed_C2")),
        ("r_131", "C", 50.0, 1000.0, "C-02", 1, "C-r2", ("feed_C3", "feed_C4")),
    ]
    for rid, pod, kw, wt, enc, u0, row, pair in installed:
        facility["racks"][rid] = {
            "pod": pod,
            "power_kw": kw,
            "heat_kw": kw,            # heat ~= electrical load for these racks
            "u_height": BATCH_RACK_U,
            "u_start": u0,
            "weight_kg": wt,
            "enclosure": enc,
            "row": row,
            "feed_pair": pair,
        }

    return facility


def _pod_skeleton(
    feeds: Dict[str, Tuple[float, str]],
    feed_pairs: List[Tuple[str, str]],
    rows: Dict[str, float],
    enclosures: Dict[str, Tuple[int, float]],
    fabric: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble one pod's static infrastructure (no racks)."""
    return {
        "feeds": {fid: {"capacity_kw": cap, "partner": partner}
                  for fid, (cap, partner) in feeds.items()},
        "feed_pairs": [tuple(p) for p in feed_pairs],
        "rows": {rid: {"cooling_kw": kw} for rid, kw in rows.items()},
        "enclosures": {eid: {"u_height": u, "floor_tile_cap_kg": cap}
                       for eid, (u, cap) in enclosures.items()},
        "fabric": fabric,
    }


def _fabric(
    switch_pairs: Dict[str, List[Optional[str]]],
    free_switch_pair_slots: int,
    oversub_ratio: float,
    oversub_cap: float,
) -> Dict[str, Any]:
    """Build a pod fabric. Each switch pair has 2 paths; a path's value is the
    cluster occupying it, or None if free."""
    return {
        "switch_pairs": {
            pid: {"paths": [{"in_use_by": occ} for occ in occupants]}
            for pid, occupants in switch_pairs.items()
        },
        "free_switch_pair_slots": free_switch_pair_slots,
        "oversub_ratio": oversub_ratio,
        "oversub_cap": oversub_cap,
    }


# ---------------------------------------------------------------------------
# Pure inspection helpers (used by verify_seed.py — NO solver, just arithmetic
# over the facility dict). Single-sourced so the proof reads the real data.
# ---------------------------------------------------------------------------

def all_feeds(facility: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Flat {feed_id -> {capacity_kw, partner, pod}} across every pod."""
    out: Dict[str, Dict[str, Any]] = {}
    for pod_id, pod in facility["pods"].items():
        for fid, f in pod["feeds"].items():
            out[fid] = {"capacity_kw": f["capacity_kw"], "partner": f["partner"], "pod": pod_id}
    return out


def feed_caps_full(facility: Dict[str, Any]) -> Dict[str, float]:
    """{feed_id -> capacity_kw} at full (healthy) capacity."""
    return {fid: f["capacity_kw"] for fid, f in all_feeds(facility).items()}


def feed_pair_load_kw(facility: Dict[str, Any], pair: Tuple[str, str]) -> float:
    """Total rack load (kW) currently assigned to a feed pair."""
    pair = tuple(pair)
    return sum(r["power_kw"] for r in facility["racks"].values()
               if tuple(r["feed_pair"]) == pair)


def rack_is_n_plus_1_compliant(
    facility: Dict[str, Any],
    rack_id: str,
    feed_caps: Dict[str, float],
) -> bool:
    """
    N+1 rule: a rack's feed pair must survive losing EITHER feed. With one feed of
    the pair removed, the surviving feed must still carry the whole pair load. So
    the pair is compliant iff pair_load <= min(cap(feed_a), cap(feed_b)). A rack is
    compliant iff its pair is. `feed_caps` lets the caller pass derated capacities.
    """
    a, b = tuple(facility["racks"][rack_id]["feed_pair"])
    load = feed_pair_load_kw(facility, (a, b))
    surviving_capacity = min(feed_caps[a], feed_caps[b])
    return load <= surviving_capacity


def pod_power_n_plus_1_headroom_kw(facility: Dict[str, Any], pod_id: str) -> float:
    """Spare N+1 power (kW) a pod can offer NEW load: sum over its feed pairs of
    max(0, min(cap_a, cap_b) - current_pair_load)."""
    caps = feed_caps_full(facility)
    total = 0.0
    for pair in facility["pods"][pod_id]["feed_pairs"]:
        a, b = tuple(pair)
        total += max(0.0, min(caps[a], caps[b]) - feed_pair_load_kw(facility, (a, b)))
    return total


def pod_thermal_headroom_kw(facility: Dict[str, Any], pod_id: str) -> float:
    """Spare cooling (kW) across a pod's rows: sum(row cooling - installed heat)."""
    racks = [r for r in facility["racks"].values() if r["pod"] == pod_id]
    total = 0.0
    for row_id, row in facility["pods"][pod_id]["rows"].items():
        used = sum(r["heat_kw"] for r in racks if r["row"] == row_id)
        total += max(0.0, row["cooling_kw"] - used)
    return total


def pod_free_u(facility: Dict[str, Any], pod_id: str) -> int:
    """Total free rack-units across a pod's enclosures."""
    racks = [r for r in facility["racks"].values() if r["pod"] == pod_id]
    total = 0
    for enc_id, enc in facility["pods"][pod_id]["enclosures"].items():
        used = sum(r["u_height"] for r in racks if r["enclosure"] == enc_id)
        total += enc["u_height"] - used
    return total


def pod_weight_headroom_kg(facility: Dict[str, Any], pod_id: str) -> float:
    """Spare floor weight (kg) across a pod's enclosures."""
    racks = [r for r in facility["racks"].values() if r["pod"] == pod_id]
    total = 0.0
    for enc_id, enc in facility["pods"][pod_id]["enclosures"].items():
        used = sum(r["weight_kg"] for r in racks if r["enclosure"] == enc_id)
        total += max(0.0, enc["floor_tile_cap_kg"] - used)
    return total


def pod_free_400g_paths(facility: Dict[str, Any], pod_id: str) -> int:
    """Count of free (unoccupied) redundant 400G paths in a pod."""
    count = 0
    for sp in facility["pods"][pod_id]["fabric"]["switch_pairs"].values():
        count += sum(1 for p in sp["paths"] if p["in_use_by"] is None)
    return count


def pod_fabric_expansion_slots(facility: Dict[str, Any], pod_id: str) -> int:
    """How many NEW 400G switch pairs the pod can physically rack."""
    return facility["pods"][pod_id]["fabric"]["free_switch_pair_slots"]


def pod_reachable_400g_paths(facility: Dict[str, Any], pod_id: str) -> int:
    """Max redundant 400G paths a pod could reach = free now + expansion * paths/pair."""
    return (pod_free_400g_paths(facility, pod_id)
            + pod_fabric_expansion_slots(facility, pod_id) * PATHS_PER_SWITCH_PAIR)


# -- batch requirement helpers --------------------------------------------

def batch_required_kw() -> float:
    return BATCH_SIZE * BATCH_RACK_KW


def batch_required_u() -> int:
    return BATCH_SIZE * BATCH_RACK_U


def batch_required_weight_kg() -> float:
    return BATCH_SIZE * BATCH_RACK_WEIGHT_KG


# ---------------------------------------------------------------------------
# The demo batch + the two ConstraintSpecs (Contract A)
# ---------------------------------------------------------------------------

def batch_8x40kw() -> List[NewRack]:
    """The demo batch: jal_1..jal_8, 40kW / 4U each, one affinity cluster
    (infcluster_A), 400G fabric. Drops straight into ConstraintSpec.new_racks."""
    return [
        NewRack(
            id=f"jal_{i}",
            power_kw=BATCH_RACK_KW,
            u_height=BATCH_RACK_U,
            weight_kg=BATCH_RACK_WEIGHT_KG,
            fabric_class=BATCH_FABRIC_CLASS,
            cluster_id=BATCH_CLUSTER_ID,
        )
        for i in range(1, BATCH_SIZE + 1)
    ]


def spec_place_batch() -> ConstraintSpec:
    """
    The `place_batch` ConstraintSpec for the 8x40kW Jalapeno demo: the cluster, the
    three objectives, and the reconciled constraints (power/thermal/fabric/affinity
    hard; contiguity soft). The data guarantees only Pod C can host it (with one new
    400G switch pair).
    """
    return ConstraintSpec(
        request_id="demo-place-batch",
        mode="place_batch",
        new_racks=batch_8x40kw(),
        objectives=["min_spend", "max_resilience", "max_future_headroom"],
        constraints=[
            Constraint(type="power_n_plus_1", hard=True, confidence=0.99, source="bms-feed-telemetry"),
            Constraint(type="thermal_zone", hard=True, confidence=0.95, source="crac-telemetry"),
            Constraint(type="fabric_oversub", hard=True, confidence=0.92, source="netbox"),
            Constraint(type="affinity", hard=True, confidence=0.97, source="workload-placement-policy"),
            Constraint(type="contiguity", hard=False, confidence=0.70, source="dcim-floorplan"),
        ],
    )


def spec_feed_derate() -> ConstraintSpec:
    """
    The `revalidate` ConstraintSpec for the break moment: a healthy facility plus a
    feed_B2 derate (140 -> 130 kW). The data guarantees exactly {r_113, r_118, r_124}
    tip into N+1 violation.
    """
    return ConstraintSpec(
        request_id="demo-feed-derate",
        mode="revalidate",
        new_racks=[],
        objectives=["max_resilience"],
        constraints=[
            Constraint(type="power_n_plus_1", hard=True, confidence=0.99, source="bms-feed-telemetry"),
        ],
        change_event=ChangeEvent(
            type="feed_derate",
            target="feed_B2",
            new_capacity_kw=FEED_B2_DERATED_KW,
        ),
    )


# ---------------------------------------------------------------------------
# Module-level exports the rest of the demo imports.
# ---------------------------------------------------------------------------

#: Alias kept so `data/twin.py` (and the solver) can wrap the seed facility.
seed_facility = build_facility

SPEC_PLACE_BATCH: ConstraintSpec = spec_place_batch()
SPEC_FEED_DERATE: ConstraintSpec = spec_feed_derate()
