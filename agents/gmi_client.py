"""
agents/gmi_client.py — GMI client helper.  (STUB — Dev B)

GMI is OpenAI-compatible. We talk to it with the OpenAI SDK pointed at GMI_BASE_URL,
authenticating with GMI_API_KEY. This module centralizes that so every agent gets a
consistently configured client, and so model names live in one place.

The real implementation lives on branch `agents`.
"""

from __future__ import annotations

import os

# Role -> model name. Single source of truth; see agents/CLAUDE.md.
MODELS = {
    "reconciler": "nemotron-3-super",
    "source_reader": "nemotron-3-nano",
    "explainer": "gpt-5.4",
    "explainer_fallback": "nemotron-3-super",
    "risk": "deepseek-v4-pro",      # independent family on purpose
    "forecaster": "nemotron-3-super",
}


def get_client(model_name: str):
    """
    Return an OpenAI-SDK client configured for GMI, paired with the model to use.

    Reads GMI_BASE_URL and GMI_API_KEY from the environment and points the OpenAI
    client at GMI's OpenAI-compatible endpoint.

    Args:
        model_name: a key from MODELS (e.g. "reconciler") or a literal model id.

    Returns:
        Whatever the agents settle on (e.g. a tuple of (client, resolved_model_id)).

    Example (to be implemented on branch `agents`):

        from openai import OpenAI
        client = OpenAI(
            base_url=os.environ["GMI_BASE_URL"],
            api_key=os.environ["GMI_API_KEY"],
        )
        return client, MODELS.get(model_name, model_name)
    """
    raise NotImplementedError("Dev B implements get_client() on branch `agents`.")
