"""
solver/_smoke_pareto.py — quick Pareto smoke (NOT a gate, NOT committed-law).

Runs compute_pareto() on the canonical feasible spec (SPEC_PLACE_BATCH) and prints the
three plans, then runs an EXPLICIT pairwise dominance check and asserts that no plan
dominates another (the Pareto non-domination contract).

    .venv/bin/python -m solver._smoke_pareto
"""

from __future__ import annotations

from typing import Any, Dict

from data.seed import SPEC_PLACE_BATCH
from solver.pareto import compute_pareto


def dominates(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """a dominates b iff a is at-least-as-good on ALL three axes (spend lower = better;
    resilience / future_headroom higher = better) and strictly better on at least one."""
    not_worse = (
        a["new_spend_usd"] <= b["new_spend_usd"]
        and a["resilience"] >= b["resilience"]
        and a["future_headroom"] >= b["future_headroom"]
    )
    strictly_better = (
        a["new_spend_usd"] < b["new_spend_usd"]
        or a["resilience"] > b["resilience"]
        or a["future_headroom"] > b["future_headroom"]
    )
    return not_worse and strictly_better


def main() -> None:
    plans = compute_pareto(SPEC_PLACE_BATCH)

    print("=" * 72)
    print("RackPilot Pareto — smoke: compute_pareto(SPEC_PLACE_BATCH)")
    print("=" * 72)
    print(f"{'label':>14} | {'new_spend_usd':>14} | {'resilience':>10} | "
          f"{'future_headroom':>15}")
    print("-" * 72)
    for p in plans:
        print(f"{p['label']:>14} | {p['new_spend_usd']:>14,.0f} | "
              f"{p['resilience']:>10.1f} | {p['future_headroom']:>15.1f}")

    assert len(plans) == 3, f"expected 3 plans, got {len(plans)}"

    print("-" * 72)
    print("pairwise dominance check (X dominates Y?):")
    any_domination = False
    for i, a in enumerate(plans):
        for j, b in enumerate(plans):
            if i == j:
                continue
            d = dominates(a, b)
            any_domination = any_domination or d
            verdict = "DOMINATES" if d else "does not dominate"
            print(f"    {a['label']:>14}  {verdict:>17}  {b['label']:<14}")

    print("-" * 72)
    assert not any_domination, "FAIL: a plan dominates another — frontier is not Pareto"
    print("PASS: all 3 plans are mutually non-dominated (genuine Pareto frontier).")
    print("=" * 72)


if __name__ == "__main__":
    main()
