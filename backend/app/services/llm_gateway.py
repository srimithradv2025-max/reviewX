"""Multi-provider LLM gateway with automatic failover.

Providers are tried in order; the first successful completion wins. When no
provider is configured (or every provider fails) ``generate_text`` raises
``AllProvidersFailedError`` so callers can degrade to static guidance.
"""

import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

_STATIC_EXPLANATION = (
    "Summary: API key exposed in source code. "
    "Move secret to an environment variable."
)


class AllProvidersFailedError(RuntimeError):
    """No LLM provider is configured, or every configured provider failed."""


def _providers() -> list[tuple[str, str, str]]:
    """(endpoint, api key, model) triples for every configured provider."""
    providers: list[tuple[str, str, str]] = []
    if CEREBRAS_KEY:
        providers.append(
            (
                "https://api.cerebras.ai/v1/chat/completions",
                CEREBRAS_KEY,
                "llama-3.3-70b",
            )
        )
    if OPENROUTER_KEY:
        providers.append(
            (
                "https://openrouter.ai/api/v1/chat/completions",
                OPENROUTER_KEY,
                "deepseek/deepseek-v4-flash",
            )
        )
    return providers


async def generate_text(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 600,
) -> str:
    """Return a completion from the first provider that answers."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for url, key, model in _providers():
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            continue  # Failover to the next provider.

    raise AllProvidersFailedError(
        "No LLM provider returned a completion; set CEREBRAS_API_KEY or "
        "OPENROUTER_API_KEY."
    )


async def generate_llm_explanation(prompt: str) -> str:
    """Explanation helper that never raises: falls back to static guidance."""
    try:
        return await generate_text(prompt)
    except AllProvidersFailedError:
        return _STATIC_EXPLANATION
