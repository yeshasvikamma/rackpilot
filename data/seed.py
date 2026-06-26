"""
data/seed.py — the seed facility and demo scenarios.  (STUB — Dev A)

Builds RackPilot's ground-truth facility: pods, rows, rack enclosures, power feeds
(with their N+1 pairing), per-row cooling/heat budgets, network fabric ports +
oversubscription, and the racks already installed. Also produces the canned scenarios
the demo drives (the healthy baseline, the 8x40kW batch, the feed-derate break).

Pure Python. No LLM. No network. Deterministic: same call → same facility.

Implementation lives on branch `solver`. These are signatures + docstrings only.
"""

from __future__ import annotations

from typing import Any, Dict, List

from contracts import ConstraintSpec


def seed_facility() -> Dict[str, Any]:
    """
    Build and return the healthy baseline facility as a plain dict (pods, rows,
    enclosures, power feeds with N+1 pairing, cooling budgets, fabric, installed
    racks). This is the version-0 ground truth the DigitalTwin wraps.

    Returns:
        A facility state dict (the exact schema is Dev A's to define internally;
        it never crosses the contract boundary).
    """
    raise NotImplementedError("Dev A implements seed_facility() on branch `solver`.")


def batch_8x40kw() -> List[Dict[str, Any]]:
    """
    Return the demo batch: 8 racks at 40kW each (OpenAI Jalapeño-class), N+1, that
    only fit in Pod C. Shaped to drop straight into ConstraintSpec.new_racks.
    """
    raise NotImplementedError("Dev A implements batch_8x40kw() on branch `solver`.")


def spec_place_batch() -> ConstraintSpec:
    """
    Build the `place_batch` ConstraintSpec for the 8x40kW demo: the racks, the
    objectives, and the reconciled hard/soft constraints. Used by the solver gate
    `test_place_batch`.
    """
    raise NotImplementedError("Dev A implements spec_place_batch() on branch `solver`.")


def spec_feed_derate() -> ConstraintSpec:
    """
    Build the `revalidate` ConstraintSpec for the break moment: a healthy facility
    plus a power-feed derate ChangeEvent. Used by the solver gate `test_break`,
    which expects newly_violating == ["r_113", "r_118", "r_124"].
    """
    raise NotImplementedError("Dev A implements spec_feed_derate() on branch `solver`.")
