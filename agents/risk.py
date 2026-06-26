"""Layer 3 adversarial critique: challenge a Pareto plan against the solver result."""

from __future__ import annotations

from contracts import ConstraintSpec, ParetoPlan, SolverResult
from agents.gmi_client import chat


def critique(result: SolverResult, plan: ParetoPlan) -> str:
    placements = "\n".join(
        f"- {p.rack_id}: pod {p.pod}, {p.rack_enclosure} U{p.u_start}"
        for p in result.placements
    ) or "None"
    violations = "\n".join(
        f"- {v.rack_id} in pod {v.pod}, rule {v.rule}: {v.detail}"
        for v in result.violations
    ) or "None"
    iis = "\n".join(
        f"- constraints {i.constraints}: {i.message}" for i in result.iis
    ) or "None"

    prompt = (
        "You are an adversarial risk reviewer. Challenge this plan. Find weaknesses, hidden costs, "
        "safety risks, or unconsidered failure modes. Be specific and cite the data provided. "
        "Do not recommend an alternative — only challenge. Be concise, under 200 words.\n\n"
        f"Status: {result.status}\n\n"
        f"Placements:\n{placements}\n\n"
        f"Violations:\n{violations}\n\n"
        f"IIS:\n{iis}\n\n"
        f"Plan under review: {plan.label}\n"
        f"Spend: ${plan.new_spend_usd:,.0f}\n"
        f"Resilience: {plan.resilience:.2f}\n"
        f"Headroom: {plan.future_headroom:.2f}"
    )
    response = chat("risk", [{"role": "user", "content": prompt}], max_tokens=2048)
    if not response:
        return "Risk review unavailable — model returned empty response."
    return response


if __name__ == "__main__":
    from api.mock_solver import solve

    result = solve(ConstraintSpec(request_id="demo-risk", mode="place_batch"))
    print(critique(result, result.pareto_plans[0]))
