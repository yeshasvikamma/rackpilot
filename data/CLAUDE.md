# data/ — Dev A (branch `solver`)

**You own this directory.** Pure Python. **No LLM calls, no network, no API keys.**

This is the facility's ground truth and the digital twin the solver reasons over:

- `seed.py` — build the seed facility (pods, rows, enclosures, power feeds, cooling
  units, fabric, existing racks) and the demo scenarios.
- `twin.py` — `DigitalTwin`: holds facility state, applies a `ChangeEvent`, and diffs
  two versions. This is what the **break moment** mutates (a feed derate).

## Rules

- You **consume `ConstraintSpec` and produce `SolverResult`** per `contracts.py`.
  **Do not change those shapes here.** A contract change is a joint decision with Dev B.
- **Do not touch `agents/`, `api/`, or `ui/`.** Those are Dev B's.
- Stay deterministic. Same inputs → same facility → same diff, every time.
- Your definition of done is the **3 tests in `solver/test_solver.py` passing** (remove
  their `xfail` marks once the real solver + twin make them pass).

## Where this fits

`data/` feeds `solver/`. The twin produces the facility state; the solver places racks
against it and, on a change event, re-solves and reports the diff. Keep the two cleanly
separated: `data/` knows the facility, `solver/` knows the math.
