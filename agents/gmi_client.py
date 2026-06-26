"""GMI Cloud OpenAI-compatible client for RackPilot agents."""

import os

from dotenv import load_dotenv
import openai

load_dotenv()

GMI_BASE_URL = os.getenv("GMI_BASE_URL")
GMI_API_KEY = os.getenv("GMI_API_KEY")

MODELS = {
    "reconciler": "nvidia/nemotron-3-ultra-550b-a55b",
    "source_reader": "openai/gpt-5.4-nano",
    "explainer": "openai/gpt-5.4",
    "risk": "deepseek-ai/DeepSeek-V4-Pro",
    "forecaster": "nvidia/nemotron-3-ultra-550b-a55b",
}


def get_client():
    return openai.OpenAI(base_url=GMI_BASE_URL, api_key=GMI_API_KEY)


def chat(role: str, messages: list, max_tokens: int = 512) -> str:
    if role not in MODELS:
        raise ValueError(f"Unknown role: {role!r}. Valid roles: {list(MODELS)}")
    resp = get_client().chat.completions.create(
        model=MODELS[role],
        messages=messages,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    test_msg = [{"role": "user", "content": "Reply with OK and your model name. Nothing else."}]
    for role in MODELS:
        try:
            result = chat(role, test_msg)
            print(f"[{role}] {result}")
        except Exception as e:
            print(f"[{role}] ERROR: {e}")
