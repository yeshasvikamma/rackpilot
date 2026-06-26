"""
data/twin.py — the DigitalTwin.  (STUB — Dev A)

A versioned model of the facility. Holds state, applies a ChangeEvent to produce a
new version, and diffs two versions to report what newly violates. This is the object
the **break moment** mutates: apply a feed derate, re-solve, surface newly_violating.

Pure Python. No LLM. No network. Deterministic.

Implementation lives on branch `solver`. This is the class skeleton only.
"""

from __future__ import annotations

from typing import Any, Dict

from contracts import ChangeEvent, FacilityDiff


class DigitalTwin:
    """
    A versioned snapshot of the facility's state.

    Typical use by the solver:
        twin = DigitalTwin(seed_facility())
        new_twin = twin.apply_change(change_event)   # returns next version
        diff = twin.diff(new_twin)                    # what newly violates
    """

    def __init__(self, state: Dict[str, Any], version: int = 0) -> None:
        """Wrap an initial facility `state` dict at the given `version`."""
        self.state = state
        self.version = version
        raise NotImplementedError(
            "Dev A implements DigitalTwin on branch `solver`."
        )

    def apply_change(self, change: ChangeEvent) -> "DigitalTwin":
        """
        Apply a ChangeEvent (e.g. a power-feed derate) and return a NEW DigitalTwin
        at version+1. Must not mutate self — versions are immutable so we can diff.
        """
        raise NotImplementedError(
            "Dev A implements DigitalTwin.apply_change() on branch `solver`."
        )

    def diff(self, other: "DigitalTwin") -> FacilityDiff:
        """
        Compare this twin against `other` and return a FacilityDiff (Contract B):
        version_from, version_to, and the list of rack ids that are newly violating.
        """
        raise NotImplementedError(
            "Dev A implements DigitalTwin.diff() on branch `solver`."
        )
