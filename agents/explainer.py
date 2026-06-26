"""Layer 3 explanation: turn a SolverResult into engineer-facing prose."""

from __future__ import annotations

from contracts import ConstraintSpec, SolverResult
from agents.gmi_client import chat


def explain(result: SolverResult) -> str:
    placements = "\n".join(
        f"- {p.rack_id}: pod {p.pod}, {p.rack_enclosure} U{p.u_start}"
        for p in result.placements
    ) or "None"
    pareto = "\n".join(
        f"- {p.label}: ${p.new_spend_usd:,.0f}, resilience {p.resilience:.2f}, headroom {p.future_headroom:.2f}"
        for p in result.pareto_plans
    ) or "None"
    violations = "\n".join(
        f"- {v.rack_id} in pod {v.pod}, rule {v.rule}: {v.detail}"
        for v in result.violations
    ) or "None"
    iis = "\n".join(
        f"- constraints {i.constraints}: {i.message}" for i in result.iis
    ) or "None"

    prompt = (
        "You are RackPilot's explainer. Write clear engineer-facing prose from this solver result. "
        "Do not contradict or override the solver.\n\n"
        f"Status: {result.status}\n\n"
        f"Placements:\n{placements}\n\n"
        f"Pareto plans:\n{pareto}\n\n"
        f"Violations:\n{violations}\n\n"
        f"IIS:\n{iis}\n\n"
        "Cover: what the solver decided, why violations exist, what the IIS means in plain English, "
        "and which Pareto plan you recommend and why."
    )
    return chat("explainer", [{"role": "user", "content": prompt}]) or ""


if __name__ == "__main__":
    from api.mock_solver import solve

    result = solve(ConstraintSpec(request_id="demo-explain", mode="place_batch"))
    print(explain(result))
