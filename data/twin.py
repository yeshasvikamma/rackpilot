"""
data/twin.py — the DigitalTwin.  (Dev A, branch `solver`)

A versioned, IMMUTABLE model of the facility. It holds an ordered list of facility
states (version 0 = the seed `build_facility()`), applies a `ChangeEvent` to produce a
NEW version without ever mutating prior ones, and diffs two versions to report which
racks newly violate N+1. This is the object the **break moment** mutates: derate
`feed_B2`, re-evaluate, surface `newly_violating`.

Pure Python. No LLM. No network. Deterministic.

SINGLE SOURCE OF TRUTH
----------------------
The twin NEVER reimplements the N+1 math. It reuses `data/seed.py`'s helpers
(`build_facility`, `feed_caps_full`, `all_feeds`, `rack_is_n_plus_1_compliant`) so the
twin's diff and the seed's verification agree by construction.

The `diff()` return matches the `SolverResult.facility_diff` shape in contracts.py
(`FacilityDiff`: version_from:int, version_to:int, newly_violating:List[str]).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple, Union

from contracts import ChangeEvent

from data.seed import (
    all_feeds,
    build_facility,
    feed_caps_full,
    rack_is_n_plus_1_compliant,
)

# Versions are labeled "T0", "T1", ... where the integer is the version index.
_LABEL_PREFIX = "T"

#: Canonical demo order for newly_violating (the break racks, in board order).
_CANONICAL_BREAK_ORDER: List[str] = ["r_113", "r_118", "r_124"]

# A version selector may be a label ("T0"), an int index (0), or None (= latest).
VersionRef = Union[str, int, None]


def _label(index: int) -> str:
    return f"{_LABEL_PREFIX}{index}"


class DigitalTwin:
    """
    A versioned snapshot history of the facility.

    Typical use by the solver / the break moment:
        twin = DigitalTwin()                              # version "T0" = seed
        v1 = twin.apply_change(change_event)              # returns "T1"
        diff = twin.diff("T0", v1)                        # what newly violates
        twin.get_state("T0")  # is byte-for-byte the original — never mutated
    """

    def __init__(self, facility: Optional[Dict[str, Any]] = None) -> None:
        """
        Wrap an initial facility as version 0 ("T0"). With no argument, the seed
        facility (`build_facility()`) is used. The initial state is deep-copied so
        no external reference can mutate the twin's history.
        """
        base = facility if facility is not None else build_facility()
        self._states: List[Dict[str, Any]] = [copy.deepcopy(base)]

    # -- version bookkeeping ------------------------------------------------

    def versions(self) -> List[str]:
        """All version labels in order, e.g. ["T0", "T1"]."""
        return [_label(i) for i in range(len(self._states))]

    @property
    def latest_version(self) -> str:
        """The most recent version label."""
        return _label(len(self._states) - 1)

    def _resolve(self, version: VersionRef) -> int:
        """Normalize a label/int/None selector to an integer version index."""
        if version is None:
            return len(self._states) - 1
        if isinstance(version, bool):  # guard: bool is an int subclass
            raise TypeError(f"invalid version selector: {version!r}")
        if isinstance(version, int):
            idx = version
        elif isinstance(version, str) and version.startswith(_LABEL_PREFIX):
            try:
                idx = int(version[len(_LABEL_PREFIX):])
            except ValueError:
                raise KeyError(f"unknown version label: {version!r}")
        else:
            raise KeyError(f"unknown version selector: {version!r}")
        if not (0 <= idx < len(self._states)):
            raise KeyError(f"version out of range: {version!r} (have {self.versions()})")
        return idx

    def get_state(self, version: VersionRef = None) -> Dict[str, Any]:
        """
        Return the facility dict for `version` (label, int index, or None=latest).

        Returns the twin's live stored state for that version. Prior versions are
        never mutated by `apply_change`, so reading T0 back always shows the seed.
        Treat the result as read-only.
        """
        return self._states[self._resolve(version)]

    # -- the immutable change application -----------------------------------

    @staticmethod
    def _coerce_change(change: Union[ChangeEvent, Dict[str, Any]]) -> Tuple[str, str, Optional[float]]:
        """Accept a contracts.ChangeEvent or the equivalent dict; return
        (type, target, new_capacity_kw)."""
        if isinstance(change, ChangeEvent):
            return change.type, change.target, change.new_capacity_kw
        if isinstance(change, dict):
            return change.get("type"), change.get("target"), change.get("new_capacity_kw")
        raise TypeError(f"apply_change expects ChangeEvent or dict, got {type(change).__name__}")

    def apply_change(self, change: Union[ChangeEvent, Dict[str, Any]]) -> str:
        """
        Apply a ChangeEvent on top of the LATEST version and append the result as a
        NEW version, returning its label (e.g. "T1"). All prior versions are left
        byte-for-byte unchanged — the new state is a deep copy mutated in isolation.

        Supported `change.type`:
            "feed_derate" — set the target feed's capacity_kw to new_capacity_kw
                            in the new version only.
        """
        ctype, target, new_capacity_kw = self._coerce_change(change)
        new_state = copy.deepcopy(self._states[-1])

        if ctype == "feed_derate":
            self._apply_feed_derate(new_state, target, new_capacity_kw)
        else:
            raise ValueError(f"unsupported change_event type: {ctype!r}")

        self._states.append(new_state)
        return self.latest_version

    @staticmethod
    def _apply_feed_derate(state: Dict[str, Any], target: str, new_capacity_kw: Optional[float]) -> None:
        """Set `target` feed's capacity_kw to `new_capacity_kw` in `state` (mutated
        in place — caller passes a fresh deep copy)."""
        if new_capacity_kw is None:
            raise ValueError("feed_derate requires new_capacity_kw")
        for pod in state["pods"].values():
            if target in pod["feeds"]:
                pod["feeds"][target]["capacity_kw"] = float(new_capacity_kw)
                return
        raise KeyError(f"feed_derate target not found: {target!r}")

    # -- diff ---------------------------------------------------------------

    def diff(self, v_from: VersionRef, v_to: VersionRef) -> Dict[str, Any]:
        """
        Compare two versions and report which racks NEWLY violate N+1 going from
        `v_from` to `v_to`: racks that were N+1-compliant under v_from's feed caps
        and violate under v_to's feed caps.

        Returns a dict matching contracts.FacilityDiff:
            {"version_from": int, "version_to": int, "newly_violating": [rack_id, ...]}
        ordered to the canonical demo order (["r_113", "r_118", "r_124"]).

        N+1 compliance is delegated to seed.rack_is_n_plus_1_compliant — the twin
        never reimplements the math.
        """
        i_from = self._resolve(v_from)
        i_to = self._resolve(v_to)
        s_from = self._states[i_from]
        s_to = self._states[i_to]

        caps_from = feed_caps_full(s_from)   # each version's own (possibly derated) caps
        caps_to = feed_caps_full(s_to)

        newly: List[str] = []
        for rack_id in s_to["racks"]:
            was_ok = rack_is_n_plus_1_compliant(s_from, rack_id, caps_from)
            now_ok = rack_is_n_plus_1_compliant(s_to, rack_id, caps_to)
            if was_ok and not now_ok:
                newly.append(rack_id)

        return {
            "version_from": i_from,
            "version_to": i_to,
            "newly_violating": _canonical_order(newly),
        }

    # -- convenience --------------------------------------------------------

    def feed_capacity(self, feed_id: str, version: VersionRef = None) -> float:
        """The capacity_kw of `feed_id` in the given version (reuses seed.all_feeds)."""
        return all_feeds(self.get_state(version))[feed_id]["capacity_kw"]


def _canonical_order(rack_ids: List[str]) -> List[str]:
    """Order rack ids by the canonical demo order first, then any extras naturally."""
    in_canon = [r for r in _CANONICAL_BREAK_ORDER if r in rack_ids]
    extras = sorted(r for r in rack_ids if r not in _CANONICAL_BREAK_ORDER)
    return in_canon + extras
