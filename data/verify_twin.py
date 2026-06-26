"""
data/verify_twin.py — Phase 1 GATE 2 (twin).  (Dev A, branch `solver`)

Proves, with NO solver, that the DigitalTwin is versioned and IMMUTABLE and that the
break moment works end to end on the data:

  * version T0 = the seed facility (feed_B2 at 140 kW).
  * apply the feed_B2 derate (SPEC_FEED_DERATE.change_event) -> new version T1.
  * IMMUTABILITY: T0's feed_B2 is STILL 140 kW after the change (read back from
    twin.get_state("T0")).
  * T1's feed_B2 == 130 kW.
  * diff(T0, T1).newly_violating == ["r_113", "r_118", "r_124"] exactly.

Run:  python data/verify_twin.py   (use the .venv interpreter — it has pydantic)
Exits 0 if every check passes, nonzero (1) if any check fails.
"""

from __future__ import annotations

import os
import sys

# Make repo root importable whether run as `python data/verify_twin.py` or `-m`.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.seed import SPEC_FEED_DERATE, all_feeds  # noqa: E402
from data.twin import DigitalTwin  # noqa: E402

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


def feed_b2_cap(twin: DigitalTwin, version: str) -> float:
    """Read feed_B2's capacity directly out of a version's stored state."""
    state = twin.get_state(version)
    return all_feeds(state)["feed_B2"]["capacity_kw"]


def main() -> int:
    hr("DIGITAL TWIN — versioning + immutable change apply")
    twin = DigitalTwin()
    v0 = "T0"
    print(f"   versions after init       : {twin.versions()}")
    check(twin.versions() == ["T0"], "fresh twin has exactly version T0")

    # Snapshot feed_B2 in v0 BEFORE any change.
    snap_v0 = feed_b2_cap(twin, v0)
    print(f"   T0 feed_B2 capacity (snap): {snap_v0:.0f} kW")
    check(snap_v0 == 140.0, "T0 feed_B2 starts at 140 kW")

    # Apply the demo derate -> new version.
    ce = SPEC_FEED_DERATE.change_event
    print(f"\n   applying change_event     : {ce.type} target={ce.target} "
          f"new_capacity_kw={ce.new_capacity_kw:.0f}")
    v1 = twin.apply_change(ce)
    print(f"   new version returned      : {v1}")
    print(f"   versions after apply      : {twin.versions()}")
    check(v1 == "T1", "apply_change returned a NEW version T1")

    # --------------------------------------------------------- immutability
    hr("IMMUTABILITY — prior version unchanged")
    after_v0 = feed_b2_cap(twin, v0)
    print(f"   T0 feed_B2 BEFORE change  : {snap_v0:.0f} kW")
    print(f"   T0 feed_B2 AFTER  change  : {after_v0:.0f} kW")
    check(after_v0 == snap_v0 == 140.0,
          "T0 feed_B2 is STILL 140 kW after the change (T0 not mutated)")

    # --------------------------------------------------------- new version
    hr("NEW VERSION — derate landed on T1 only")
    v1_cap = feed_b2_cap(twin, v1)
    print(f"   T1 feed_B2 capacity       : {v1_cap:.0f} kW")
    check(v1_cap == 130.0, "T1 feed_B2 == 130 kW")

    # --------------------------------------------------------- the break diff
    hr("DIFF(T0, T1) — newly violating racks")
    d = twin.diff(v0, v1)
    print(f"   version_from / version_to : {d['version_from']} -> {d['version_to']}")
    print(f"   newly_violating           : {d['newly_violating']}")
    print(f"   expected                  : ['r_113', 'r_118', 'r_124']")
    check(d["newly_violating"] == ["r_113", "r_118", "r_124"],
          "diff(T0, T1).newly_violating == ['r_113', 'r_118', 'r_124'] exactly")

    # ----------------------------------------------------------------- verdict
    hr("VERDICT")
    if _FAILURES:
        print(f"   {len(_FAILURES)} CHECK(S) FAILED:")
        for f in _FAILURES:
            print(f"     - {f}")
        print("\n   GATE 2 (twin): FAILED")
        return 1
    print("   ALL CHECKS PASSED")
    print("   GATE 2 (twin): GREEN — versioned, immutable, break moment fires on the data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
