"""Async LLM gateway with automatic provider failover for ReviewX.

Providers are tried in order until one succeeds:

    Groq        -> llama-3.3-70b-versatile
    Google      -> gemini-2.0-flash-exp
    OpenRouter  -> deepseek/deepseek-chat:free

API keys are read from environment variables (``GROQ_API_KEY``,
``GEMINI_API_KEY``, ``OPENROUTER_API_KEY``) and are **never** included in
responses, log messages, or raised exceptions.  Any provider failure -- missing
credentials, 429 rate limits, timeouts, 5xx, malformed responses -- moves the
call to the next configured provider.  When every provider fails an
``AllProvidersFailedError`` is raised with a safe, key-free message.

The module keeps the request-shaping logic in pure functions (``build_payload``,
``extract_response``) so it is easy to unit test without a network or real keys.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

# Timeout used when a provider explicitly tells us to back off (Retry-After).
_RATE_LIMIT_STATUS_CODES = frozenset({429})

# -----------------------------------------------------------------------------
# Exceptions (safe to surface to callers / users -- never carry secrets)
# -----------------------------------------------------------------------------


class LLMProviderError(RuntimeError):
    """Base class for all LLM gateway errors."""


class AllProvidersFailedError(LLMProviderError):
    """Raised after every configured provider was attempted and failed."""


class RateLimitError(LLMProviderError):
    """Raised when a provider answers with an HTTP 429 / rate-limit response."""


# -----------------------------------------------------------------------------
# Provider registry
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMProvider:
    """Static description of one upstream LLM provider."""

    name: str
    endpoint: str  # may contain a {model} placeholder
    env_key: str  # environment variable that holds the API key
    model: str
    auth: str  # "bearer" (Authorization header) or "url_query" (?key=...)


GROQ = LLMProvider(
    name="groq",
    endpoint="https://api.groq.com/openai/v1/chat/completions",
    env_key="GROQ_API_KEY",
    model="llama-3.3-70b-versatile",
    auth="bearer",
)

GEMINI = LLMProvider(
    name="gemini",
    endpoint="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    env_key="GEMINI_API_KEY",
    model="gemini-2.0-flash-exp",
    auth="url_query",
)

OPENROUTER = LLMProvider(
    name="openrouter",
    endpoint="https://openrouter.ai/api/v1/chat/completions",
    env_key="OPENROUTER_API_KEY",
    model="deepseek/deepseek-chat:free",
    auth="bearer",
)

# Failover order: Groq first, then Gemini, then OpenRouter.
PROVIDER_ORDER: tuple[LLMProvider, ...] = (GROQ, GEMINI, OPENROUTER)


# -----------------------------------------------------------------------------
# Secret redaction helpers (never let keys reach logs/exceptions)
# -----------------------------------------------------------------------------

# Redacts ?key=..., &key=..., and common high-entropy credential literals.
_SECRET_IN_URL_RE = re.compile(r"([?&](?:key|api_key|token|X-Goog-Api-Key)=)[^&\s\"']+")
_SECRET_LITERAL_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{8,}|ghp_[A-Za-z0-9]{8,}|"
    r"AIza[0-9A-Za-z_-]{8,}|Bearer\s+[A-Za-z0-9._-]{8,})\b"
)


def redact_secrets(text: str) -> str:
    """Return ``text`` with any credential-shaped substrings replaced."""
    if not text:
        return text
    redacted = _SECRET_IN_URL_RE.sub(r"\1<redacted>", text)
    redacted = _SECRET_LITERAL_RE.sub("<redacted>", redacted)
    return redacted


def safely_redact_response_value(value: Any) -> str:
    """Stringify an arbitrary value with embedded secrets scrubbed."""
    return redact_secrets(str(value))
# -----------------------------------------------------------------------------
# Pure request-shaping / response-parsing functions (unit-testable)
# -----------------------------------------------------------------------------

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": "..."}


def _openai_compatible_payload(
    provider: LLMProvider,
    messages: list[Message],
    *,
    temperature: Optional[float],
    max_tokens: Optional[int],
) -> dict[str, Any]:
    """Shape a Groq / OpenRouter (OpenAI-compatible) chat-completions body."""
    payload: dict[str, Any] = {"model": provider.model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    return payload


def _gemini_payload(
    provider: LLMProvider,
    messages: list[Message],
    *,
    temperature: Optional[float],
    max_tokens: Optional[int],
) -> dict[str, Any]:
    """Shape a Gemini generateContent body from the same message list.

    System prompts are collected into Gemini's ``systemInstruction``; the rest
    become ``contents``.
    """
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            system_parts.append(content)
        else:
            contents.append({"role": role, "parts": [{"text": content}]})

    body: dict[str, Any] = {"contents": contents}
    if system_parts:
        body["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
    if temperature is not None or max_tokens is not None:
        generation_config: dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        body["generationConfig"] = generation_config
    return body


def build_payload(
    provider: LLMProvider,
    messages: list[Message],
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> dict[str, Any]:
    """Dispatch to the right provider-specific payload shape."""
    if provider.name == "gemini":
        return _gemini_payload(provider, messages, temperature=temperature, max_tokens=max_tokens)
    return _openai_compatible_payload(
        provider, messages, temperature=temperature, max_tokens=max_tokens
    )


def _openai_compatible_text(data: dict[str, Any]) -> str:
    """Extract the assistant text from an OpenAI-compatible response."""
    return data["choices"][0]["message"]["content"]


def _gemini_text(data: dict[str, Any]) -> str:
    """Extract the assistant text from a Gemini generateContent response."""
    return data["candidates"][0]["content"]["parts"][0]["text"]


def extract_response(provider: LLMProvider, data: dict[str, Any]) -> str:
    """Dispatch to the provider-specific response parser."""
    if provider.name == "gemini":
        return _gemini_text(data)
    return _openai_compatible_text(data)  # type: ignore[no-any-return]


def normalize_messages(
    prompt: Optional[str],
    system: Optional[str],
    messages: Optional[list[Message]],
) -> list[Message]:
    """Return a canonical ``messages`` list from either a prompt or a raw list."""
    if messages is not None:
        return list(messages)
    normalized: list[Message] = []
    if system:
        normalized.append({"role": "system", "content": system})
    if prompt:
        normalized.append({"role": "user", "content": prompt})
    return normalized
# -----------------------------------------------------------------------------
# Provider selection + async failover execution
# -----------------------------------------------------------------------------


def get_api_key(provider: LLMProvider) -> Optional[str]:
    """Return the configured API key for ``provider`` (trimmed) or ``None``."""
    value = os.environ.get(provider.env_key, "")
    return value.strip() or None


def configured_providers() -> list[LLMProvider]:
    """Providers (in failover order) whose API key is present in the env."""
    return [provider for provider in PROVIDER_ORDER if get_api_key(provider)]


async def _call_provider(
    client: httpx.AsyncClient,
    provider: LLMProvider,
    payload: dict[str, Any],
) -> str:
    """POST the payload to one provider and return its assistant text.

    Raises:
        RateLimitError: on HTTP 429.
        httpx.HTTPError / KeyError / ValueError: any provider or parse failure.
    """
    api_key = get_api_key(provider)
    if not api_key:
        raise LLMProviderError(f"Missing API key for provider '{provider.name}'.")

    url = provider.endpoint.format(model=provider.model)
    headers = {"Content-Type": "application/json"}
    if provider.auth == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider.auth == "url_query":
        url = f"{url}?key={api_key}"
    else:  # pragma: no cover - defensive
        raise LLMProviderError(f"Unknown auth style '{provider.auth}'.")

    # Log the sanitized URL only -- never the key itself.
    logger.debug("POST %s (provider=%s)", redact_secrets(url), provider.name)

    response = await client.post(url, json=payload, headers=headers)

    if response.status_code in _RATE_LIMIT_STATUS_CODES:
        raise RateLimitError(
            f"{provider.name} rate limited (status {response.status_code})"
        )
    if response.status_code >= 400:
        # Never leak response bodies (they may echo keys) -- status + URL only.
        raise LLMProviderError(
            f"{provider.name} HTTP {response.status_code}: "
            f"{redact_secrets(url)}"
        )

    try:
        data = response.json()
        return extract_response(provider, data)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMProviderError(
            f"{provider.name} returned an unparseable response ({exc.__class__.__name__})."
        ) from exc


async def chat(
    messages: list[Message],
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Run ``messages`` through the first provider that succeeds.

    Providers are attempted in ``PROVIDER_ORDER``.  Missing keys, 429 rate
    limits, timeouts, HTTP errors, and malformed responses all trigger failover
    to the next provider.  Keys are never logged or exposed.

    Args:
        messages: OpenAI-style ``[{"role": ..., "content": ...}, ...]`` list.
        temperature: optional sampling temperature.
        max_tokens: optional cap on output tokens.
        client: an optional ``httpx.AsyncClient`` (useful for tests / reuse).

    Returns:
        The assistant response text.

    Raises:
        AllProvidersFailedError: when no provider is configured or all fail.
    """
    providers = configured_providers()
    if not providers:
        raise AllProvidersFailedError(
            "No LLM providers configured. Set one of: "
            "GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY."
        )

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    attempt_errors: list[str] = []
    try:
        for provider in providers:
            try:
                payload = build_payload(
                    provider,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return await _call_provider(client, provider, payload)
            except Exception as exc:  # noqa: BLE001 - failover is the point
                attempt_errors.append(
                    f"{provider.name}: {redact_secrets(str(exc))}"
                )
                logger.warning(
                    "LLM provider '%s' failed; trying next. %s",
                    provider.name,
                    redact_secrets(str(exc)),
                )
    finally:
        if owns_client:
            await client.aclose()

    raise AllProvidersFailedError(
        "All LLM providers failed: " + "; ".join(attempt_errors)
    )


async def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Convenience wrapper: build a single-turn message list and call ``chat``."""
    messages = normalize_messages(prompt, system, None)
    if not messages:
        raise ValueError("'prompt' or 'messages' must be provided.")
    return await chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        client=client,
    )


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "AllProvidersFailedError",
    "RateLimitError",
    "GROQ",
    "GEMINI",
    "OPENROUTER",
    "PROVIDER_ORDER",
    "configured_providers",
    "get_api_key",
    "build_payload",
    "extract_response",
    "normalize_messages",
    "redact_secrets",
    "chat",
    "generate_text",
]
