# agents/ — Dev B (branch `agents`)

**You own this directory.** This is Layer 1 (reconcile disagreeing sources → one
`ConstraintSpec`) and Layer 3 (explain / critique / negotiate the `SolverResult`).

You **produce `ConstraintSpec` and consume `SolverResult`** per `contracts.py`.
**Do not change those shapes here** — a contract change is a joint decision with Dev A.
**Do not touch `data/` or `solver/`.**

## The golden rule (do not break it)

**LLMs only assemble the problem and explain results. The solver decides everything.**
An agent must NEVER make a placement decision, pick a violation, or choose which plan
wins. If something is being *decided*, it belongs in `solver/`, not in a prompt.

## Build against the mock — never block on the real solver

`api/main.py` imports `solve` from `api/mock_solver.py` during development. Build the
entire agents + api + ui half against that working, hardcoded `SolverResult`. The final
integration is a one-line import swap (see root CLAUDE.md). Never wait for Dev A.

## Model assignments (GMI, OpenAI-compatible)

GMI is OpenAI-compatible: point the OpenAI SDK at `GMI_BASE_URL` using `GMI_API_KEY`
(see `agents/gmi_client.py`). Assign models per role:

| Role           | Model                        | Notes |
|----------------|------------------------------|-------|
| reconciler     | **Nemotron 3 Super**         | Layer 1, merges sources into ConstraintSpec |
| source-readers | **Nemotron 3 Nano**         | cheap/fast, one per data source |
| explainer      | **GPT-5.4** (Nemotron Super fallback) | Layer 3, human-facing narrative |
| risk           | **DeepSeek-V4-Pro**          | independent family **on purpose** (adversarial critique) |
| forecaster     | **Nemotron 3 Super**         | cut-first if time runs short |

The `risk` agent uses a deliberately different model family so its critique is not
correlated with the reconciler/explainer — it is there to disagree.

## Orchestration is plain Python

The flow in `api/main.py` is **hardcoded Python, NOT an LLM.** Agents are called in a
fixed sequence; the LLM never decides what runs next.
