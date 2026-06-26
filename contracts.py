"""
contracts.py — RackPilot's SHARED LAW.

This file defines the ONLY two data structures that cross the boundary between
the two development tracks:

    Contract A: ConstraintSpec  — what the Layer 1 agents hand TO the solver.
    Contract B: SolverResult    — what the Layer 2 solver hands BACK to the agents.

OWNERSHIP / EDITING RULE
------------------------
contracts.py is shared by BOTH branches (`solver` and `agents`). It is the one
file neither developer may change unilaterally. A change here is the ONLY thing
that can break the merge, because both halves are compiled against these shapes.

    -> Never edit contracts.py on one branch without syncing with the other dev.
    -> If you think you need a new field, STOP and have the contract conversation
       first, then change it together, then both rebase.

Everything downstream — the mock solver, the real solver, the reconciler agent,
the FastAPI app, the tests, the UI — depends on these definitions being stable.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Contract A — ConstraintSpec   (Layer 1 agents  ->  Layer 2 solver)
# ============================================================================

class NewRack(BaseModel):
    """A single rack of hardware the engineer wants to place."""

    id: str
    power_kw: float
    u_height: int
    weight_kg: float
    fabric_class: str
    cluster_id: str


class Constraint(BaseModel):
    """
    One reconciled rule the solver must respect.

    hard        True  -> must hold (came from a trusted source).
                False -> soft: may be bent, but the solver pays a penalty.
    confidence  0..1, how much Layer 1 trusts this constraint.
    source      provenance string (which data source it was reconciled from).
    """

    type: str
    hard: bool
    confidence: float = Field(ge=0.0, le=1.0)
    source: str


class ChangeEvent(BaseModel):
    """
    An infrastructure change that triggers a re-solve.

    e.g. a power feed derate, a cooling unit dropping, a new chip raising
    per-rack power. `new_capacity_kw` is optional because not every change is
    a capacity change.
    """

    type: str
    target: str
    new_capacity_kw: Optional[float] = None


class ConstraintSpec(BaseModel):
    """
    Contract A. The single reconciled problem statement produced by the Layer 1
    agents and consumed by the Layer 2 solver. The solver makes ALL decisions
    from this — agents never decide placement.
    """

    request_id: str
    mode: Literal["place_batch", "revalidate"]
    new_racks: List[NewRack] = Field(default_factory=list)
    objectives: List[str] = Field(default_factory=list)
    constraints: List[Constraint] = Field(default_factory=list)
    change_event: Optional[ChangeEvent] = None


# ============================================================================
# Contract B — SolverResult   (Layer 2 solver  ->  Layer 3 agents)
# ============================================================================

class Placement(BaseModel):
    """Where the solver decided to put one rack."""

    rack_id: str
    pod: str
    rack_enclosure: str
    u_start: int


class ParetoPlan(BaseModel):
    """One non-dominated option on the multi-objective trade-off frontier."""

    label: str
    new_spend_usd: float
    resilience: float
    future_headroom: float


class Violation(BaseModel):
    """A rule that is broken (or would be broken) for a given rack/pod."""

    rack_id: str
    pod: str
    rule: str
    detail: str


class IIS(BaseModel):
    """
    Irreducible Infeasible Subset: a MINIMAL set of constraints that together
    cannot be satisfied. This is the solver's mathematical PROOF of why no plan
    exists — the thing Layer 3 negotiates over.
    """

    constraints: List[str]
    message: str


class NewHardware(BaseModel):
    """Hardware the solver proposes buying to make a plan feasible."""

    item: str
    pod: str
    cost_usd: float


class FacilityDiff(BaseModel):
    """What changed between two facility versions after a re-solve."""

    version_from: int
    version_to: int
    newly_violating: List[str] = Field(default_factory=list)


class SolverResult(BaseModel):
    """
    Contract B. The deterministic solver's answer. The Layer 3 agents explain,
    critique, and surface this to the human — but NEVER override it.
    """

    request_id: str
    status: Literal["feasible", "infeasible"]
    placements: List[Placement] = Field(default_factory=list)
    pareto_plans: List[ParetoPlan] = Field(default_factory=list)
    violations: List[Violation] = Field(default_factory=list)
    iis: List[IIS] = Field(default_factory=list)
    new_hardware: List[NewHardware] = Field(default_factory=list)
    # Optional because a fresh place_batch has nothing to diff against; a
    # revalidate always populates it.
    facility_diff: Optional[FacilityDiff] = None
