"""Layer 1 reconciliation: merge disagreeing sources into one ConstraintSpec."""

from __future__ import annotations

import json
import re

from contracts import Constraint, ConstraintSpec, NewRack
from agents.gmi_client import chat

READER_SCHEMA = '{"power_kw": float, "fabric_class": str, "confidence": float}'


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def reconcile(sources: list[dict]) -> ConstraintSpec:
    extracted = []
    for src in sources:
        prompt = (
            f"Extract structured facts as JSON only: {READER_SCHEMA}\n"
            f"Source name: {src['name']}\n\n{src['data']}"
        )
        raw = chat("source_reader", [{"role": "user", "content": prompt}])
        facts = _parse_json(raw)
        facts["source_name"] = src["name"]
        extracted.append(facts)

    reconcile_prompt = (
        "Reconcile conflicting datacenter facts from multiple sources. "
        "Prefer authoritative dcim for nameplate values; lower confidence when sources disagree.\n"
        f"Sources:\n{json.dumps(extracted, indent=2)}\n\n"
        'Return JSON only: {"power_kw": float, "fabric_class": str, "constraints": '
        '[{"type": "power_kw"|"fabric_class", "confidence": float, "source": "dcim"|"telemetry"}]}. '
        "One constraint per reconciled fact. Set source to the winning source name."
    )
    reconciled = _parse_json(chat("reconciler", [{"role": "user", "content": reconcile_prompt}]))

    def _first(key: str, default):
        for item in extracted:
            if item.get(key) is not None:
                return item[key]
        return default

    power_kw = float(reconciled.get("power_kw", _first("power_kw", 30.0)))
    fabric_class = str(reconciled.get("fabric_class", _first("fabric_class", "400G")))

    constraints = []
    for c in reconciled.get("constraints", []):
        try:
            conf = float(c.get("confidence", 0.5))
            constraints.append(Constraint(
                type=str(c.get("type", "unknown")),
                hard=conf >= 0.8,
                confidence=conf,
                source=str(c.get("source", "unknown")),
            ))
        except (TypeError, ValueError):
            continue

    if not constraints:
        src_name = extracted[0].get("source_name", "unknown") if extracted else "unknown"
        for typ in ("power_kw", "fabric_class"):
            constraints.append(Constraint(
                type=typ, hard=False, confidence=0.5, source=src_name,
            ))

    return ConstraintSpec(
        request_id="req_001",
        mode="place_batch",
        new_racks=[NewRack(
            id="jal_1", power_kw=power_kw, u_height=4, weight_kg=1200,
            fabric_class=fabric_class, cluster_id="infcluster_A",
        )],
        constraints=constraints,
        change_event=None,
    )


if __name__ == "__main__":
    SOURCES = [
        {
            "name": "dcim",
            "data": "Rack jal_1 nameplate power: 30kW. Fabric class: 400G. This is the official design spec.",
        },
        {
            "name": "telemetry",
            "data": "Rack jal_1 measured draw: 26kW effective. Fabric port scan shows 400G available. Confidence lower due to sensor lag.",
        },
    ]
    print(reconcile(SOURCES).model_dump_json(indent=2))
