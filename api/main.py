"""
api/main.py — the /handle orchestration endpoint.  (STUB — Dev B)

FastAPI app with a single POST /handle that runs the three layers in a HARDCODED
Python sequence (the LLM never decides what runs next, and never makes a placement
decision — the solver decides everything).

THE ONE LINE THAT MATTERS FOR THE MERGE
---------------------------------------
During development we import the solver from the mock:

    from api.mock_solver import solve

The entire final integration is changing that single import to:

    from solver.model import solve

…then re-running this exact /handle flow and confirming the break moment fires through
the REAL solver. Nothing else in this file should need to change.

Run:  uvicorn api.main:app --reload
"""

from __future__ import annotations

from typing import Any, List

from fastapi import FastAPI
from pydantic import BaseModel

from contracts import Constraint, ConstraintSpec, NewRack, SolverResult

# >>> THE MERGE SWAP LIVES HERE <<<
# dev:   from api.mock_solver import solve
# final: from solver.model import solve
from api.mock_solver import solve

# Layer 1 / Layer 3 agents (stubs on main; Dev B implements on branch `agents`).
# Imported lazily inside the flow so the API still boots while they're unimplemented.
# from agents.reconciler import reconcile
from agents.explainer import explain
from agents.risk import critique

app = FastAPI(title="RackPilot", version="0.1.0")


class HandleRequest(BaseModel):
    """What the UI posts to /handle. `sources` are the raw, possibly-conflicting inputs."""

    request_id: str = "demo-1"
    mode: str = "place_batch"
    sources: List[Any] = []


class HandleResponse(BaseModel):
    """Everything the human needs to approve or reject — the approval gate."""

    spec: ConstraintSpec
    result: SolverResult
    explanation: str
    critique: str
    ticket: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "rackpilot"}


@app.post("/handle", response_model=HandleResponse)
def handle(req: HandleRequest) -> HandleResponse:
    """
    The hardcoded orchestration flow. Fixed sequence, plain Python:

        1. Layer 1: reconcile disagreeing sources -> ConstraintSpec
        2. Layer 2: solve(spec) -> SolverResult        (the ONLY decision-maker)
        3. Layer 3: explain + critique
        4. return to the human for approval

    On `main` the agents are stubs, so steps 1/3 use a hardcoded demo spec and skip the
    LLM calls — but step 2 is already live against the mock solver. As Dev B implements
    the agents, swap the demo spec for reconcile(req.sources) and fill in explain/critique.
    """

    # --- Layer 1 — skip reconcile; use demo spec built from request ---
    spec = _demo_spec(req)

    # --- Layer 2 — the solver decides everything ---
    result: SolverResult = solve(spec)

    # --- Layer 3 — explain + adversarial critique ---
    explanation = explain(result)
    critique_text = (
        critique(result, result.pareto_plans[0])
        if result.pareto_plans
        else "No plans available"
    )

    return HandleResponse(
        spec=spec,
        result=result,
        explanation=explanation,
        critique=critique_text,
        ticket="APPROVED — Pod C placement for req_001. Reviewed by RackPilot.",
    )


def _demo_spec(req: HandleRequest) -> ConstraintSpec:
    """Stand-in for the reconciler: a believable 8x40kW N+1 batch in `place_batch` mode."""
    racks = [
        NewRack(
            id=f"r_2{i:02d}",
            power_kw=40.0,
            u_height=42,
            weight_kg=1200.0,
            fabric_class="gpu-400g",
            cluster_id="jalapeno-1",
        )
        for i in range(1, 9)
    ]
    constraints = [
        Constraint(type="power_n1", hard=True, confidence=0.99, source="eaton-pdu"),
        Constraint(type="thermal_row_budget", hard=True, confidence=0.95, source="crac-telemetry"),
        Constraint(type="fabric_oversub", hard=True, confidence=0.90, source="netbox"),
        Constraint(type="space_contiguous_u", hard=True, confidence=0.98, source="dcim-floorplan"),
        Constraint(type="floor_weight", hard=False, confidence=0.60, source="structural-pdf-2019"),
    ]
    return ConstraintSpec(
        request_id=req.request_id,
        mode="place_batch",
        new_racks=racks,
        objectives=["minimize_spend", "maximize_resilience", "maximize_future_headroom"],
        constraints=constraints,
    )
