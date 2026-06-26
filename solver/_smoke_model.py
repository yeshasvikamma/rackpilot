"""
solver/_smoke_model.py — quick feasibility-core smoke (NOT a gate, NOT committed-law).

Runs the real CP-SAT solver on the canonical demo spec (SPEC_PLACE_BATCH: 8x40kW,
N+1, one affinity cluster) and prints the narrative the facility is engineered to
force: feasible, all placements in Pod C, Pod A & Pod B in violations for their real
reasons, and the one 400G switch pair Pod C must buy.

    .venv/bin/python -m solver._smoke_model
"""

from __future__ import annotations

from data.seed import SPEC_PLACE_BATCH
from solver.model import solve


def main() -> None:
    result = solve(SPEC_PLACE_BATCH)

    print("=" * 68)
    print("RackPilot feasibility core — smoke: solve(SPEC_PLACE_BATCH)")
    print("=" * 68)
    print(f"status            : {result.status}")

    pods = sorted({p.pod for p in result.placements})
    print(f"placements        : {len(result.placements)} rack(s), pod(s) = {pods}")
    for pl in result.placements:
        print(f"    {pl.rack_id:>6}  ->  pod {pl.pod}  {pl.rack_enclosure}  U{pl.u_start}")

    print("-" * 68)
    by_pod = {v.pod: v for v in result.violations}
    for pod in ("A", "B"):
        v = by_pod.get(pod)
        if v is None:
            print(f"pod {pod} violation   : (none)")
        else:
            print(f"pod {pod} violation   : {v.rule}")
            print(f"                    {v.detail}")

    print("-" * 68)
    if result.new_hardware:
        for hw in result.new_hardware:
            print(f"new_hardware      : {hw.item} @ pod {hw.pod}  ${hw.cost_usd:,.0f}")
    else:
        print("new_hardware      : (none)")
    total = sum(hw.cost_usd for hw in result.new_hardware)
    print(f"new_hardware total: ${total:,.0f}")
    print(f"iis / pareto      : {len(result.iis)} / {len(result.pareto_plans)} "
          f"(left for Terminals B / D)")
    print("=" * 68)


if __name__ == "__main__":
    main()
