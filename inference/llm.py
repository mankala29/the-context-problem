"""
Inference layer.

Wraps the Anthropic API call. The model receives a fully-constructed prompt
and has no visibility into how that prompt was assembled — it treats the
context as ground truth.
"""

import anthropic
from config import settings


def call_llm(prompt: str) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model=settings.model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    answer = next((b.text for b in response.content if b.type == "text"), "")
    tokens = response.usage.input_tokens + response.usage.output_tokens

    return {
        "answer": answer,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "total_tokens": tokens,
        "stop_reason": response.stop_reason,
    }
