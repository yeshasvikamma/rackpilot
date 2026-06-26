"""
agents/reconciler.py — Layer 1 reconciliation.  (STUB — Dev B)

Reads multiple DISAGREEING data sources and merges them into ONE ConstraintSpec,
tagging each constraint with confidence + provenance: a trusted source becomes a
HARD constraint; a stale/uncertain source becomes a SOFT constraint with a penalty.

This assembles the problem. It does NOT solve it and it does NOT decide placement.

Model: Nemotron 3 Super (source-readers: Nemotron 3 Nano). See agents/CLAUDE.md.
The real implementation lives on branch `agents`.
"""

from __future__ import annotations

from typing import Any, List

from contracts import ConstraintSpec


def reconcile(sources: List[Any]) -> ConstraintSpec:
    """
    Merge a list of (possibly conflicting) data sources into a single ConstraintSpec.

    Each source-reader (Nemotron 3 Nano) extracts candidate constraints from its
    source; the reconciler (Nemotron 3 Super) resolves conflicts and assigns
    hard/soft + confidence + source provenance per the trust rules.

    Args:
        sources: raw data sources (DCIM exports, telemetry, PDFs, NetBox, ...).

    Returns:
        Contract A, ready to hand to the solver. The solver decides everything from here.
    """
    raise NotImplementedError("Dev B implements reconcile() on branch `agents`.")
