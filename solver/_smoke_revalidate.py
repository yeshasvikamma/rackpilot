"""
solver/_smoke_revalidate.py — quick break-moment smoke (NOT a gate, NOT committed-law).

Runs the incremental revalidate on the canonical derate spec (SPEC_FEED_DERATE:
feed_B2 140 -> 130 kW) and prints the break the facility is engineered to force:
exactly r_113 / r_118 / r_124 newly violate N+1, with the facility_diff versions as
INTS and one canonical power_n_plus_1 violation per rack.

    .venv/bin/python -m solver._smoke_revalidate
"""

from __future__ import annotations

from data.seed import SPEC_FEED_DERATE
from solver.revalidate import revalidate

EXPECTED_BREAK = ["r_113", "r_118", "r_124"]


def main() -> None:
    result = revalidate(SPEC_FEED_DERATE)

    print("=" * 72)
    print("RackPilot break moment — smoke: revalidate(SPEC_FEED_DERATE)")
    print("=" * 72)
    print(f"status            : {result.status}")

    fd = result.facility_diff
    print("-" * 72)
    print("facility_diff:")
    if fd is None:
        print("    (none) — ERROR: a revalidate must populate facility_diff")
    else:
        print(f"    version_from    : {fd.version_from!r}   (type={type(fd.version_from).__name__})")
        print(f"    version_to      : {fd.version_to!r}   (type={type(fd.version_to).__name__})")
        print(f"    newly_violating : {fd.newly_violating}")
        ints_ok = isinstance(fd.version_from, int) and isinstance(fd.version_to, int)
        order_ok = fd.newly_violating == EXPECTED_BREAK
        print(f"    versions are INT: {ints_ok}")
        print(f"    == {EXPECTED_BREAK} (exact order): {order_ok}")

    print("-" * 72)
    print(f"violations        : {len(result.violations)} rack(s)")
    for v in result.violations:
        print(f"    {v.rack_id:>6}  pod {v.pod}  rule={v.rule}")
        print(f"            {v.detail}")

    print("-" * 72)
    print(f"placements / iis / pareto : {len(result.placements)} / "
          f"{len(result.iis)} / {len(result.pareto_plans)}  "
          f"(empty on the pure revalidate path)")
    print("=" * 72)


if __name__ == "__main__":
    main()
