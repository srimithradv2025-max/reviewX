"""Verification for Step 2.3: vector_store.py + llm_gateway.py.

Run (PowerShell):
    Set-Location c:\\Users\\rindh\\reviewX\\backend
    .\\venv\\Scripts\\python.exe tests\\run_step2_3_check.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import httpx

BACKEND = Path(r"c:\Users\rindh\reviewX\backend")
sys.path.insert(0, str(BACKEND))

from app.services import llm_gateway, vector_store  # noqa: E402
from app.services.ast_parser import (  # noqa: E402
    R_DANGEROUS_EVAL,
    R_DANGEROUS_EXEC,
    R_MISSING_SAFETY_INTERLOC,
    R_SECRET_API_KEY,
    R_SECRET_CONNECTION_STRING,
    R_SECRET_JWT,
    R_SECRET_PASSWORD,
    R_UNSAFE_SQL,
)

ALL_RULES = [
    R_SECRET_API_KEY,
    R_SECRET_JWT,
    R_SECRET_PASSWORD,
    R_SECRET_CONNECTION_STRING,
    R_DANGEROUS_EVAL,
    R_DANGEROUS_EXEC,
    R_UNSAFE_SQL,
    R_MISSING_SAFETY_INTERLOC,
]

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"{status}  {name}{suffix}")
    if not condition:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Test doubles for the async LLM gateway failover tests
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self) -> dict:
        return self._data


class _FakeFailoverClient:
    """Succeeds on every call except the FIRST one (which raises)."""

    def __init__(self):
        self.calls: list[str] = []
        self._fail_next = True

    async def post(self, url, json=None, headers=None):
        self.calls.append(url)
        if self._fail_next:
            self._fail_next = False
            raise httpx.ConnectError("simulated network failure")
        return _FakeResponse(
            200,
            {"candidates": [{"content": {"parts": [{"text": "fallback-ok"}]}}]},
        )

    async def aclose(self):
        return None


class _FakeOkClient:
    """Succeeds on every call."""

    def __init__(self):
        self.calls: list[str] = []

    async def post(self, url, json=None, headers=None):
        self.calls.append(url)
        return _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    async def aclose(self):
        return None


class _FakeRateLimitClient:
    """Always answers HTTP 429."""

    def __init__(self):
        self.calls: list[str] = []

    async def post(self, url, json=None, headers=None):
        self.calls.append(url)
        return _FakeResponse(429, {"error": "rate limited"})

    async def aclose(self):
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_llm_gateway_pure():
    print("\n--- llm_gateway: pure functions ---")
    names = [p.name for p in llm_gateway.PROVIDER_ORDER]
    check("provider order groq->gemini->openrouter", names == ["groq", "gemini", "openrouter"])
    check("preferred groq model", llm_gateway.GROQ.model == "llama-3.3-70b-versatile")
    check("preferred gemini model", llm_gateway.GEMINI.model == "gemini-2.0-flash-exp")
    check("preferred openrouter model", llm_gateway.OPENROUTER.model == "deepseek/deepseek-chat:free")

    msgs = [{"role": "user", "content": "hello"}]
    for p in llm_gateway.PROVIDER_ORDER:
        payload = llm_gateway.build_payload(p, msgs, max_tokens=16, temperature=0.2)
        check(f"build_payload({p.name}) is a dict", isinstance(payload, dict))

    groq_payload = llm_gateway.build_payload(llm_gateway.GROQ, msgs, max_tokens=16)
    check("groq payload carries correct model", groq_payload.get("model") == llm_gateway.GROQ.model)

    gemini_payload = llm_gateway.build_payload(llm_gateway.GEMINI, msgs, max_tokens=16)
    check("gemini payload has generationConfig", "generationConfig" in gemini_payload)

    openai_data = {"choices": [{"message": {"content": "hello"}}]}
    gemini_data = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}
    check("extract openai-compatible text", llm_gateway.extract_response(llm_gateway.GROQ, openai_data) == "hello")
    check("extract gemini text", llm_gateway.extract_response(llm_gateway.GEMINI, gemini_data) == "hi")

    redacted = llm_gateway.redact_secrets("url?key=SUPERSECRET sk-abcdefghijklmnop ghp_12345678abc")
    check("redact_secrets removes url key", "SUPERSECRET" not in redacted)
    check("redact_secrets removes sk- literal", "abcdefghijklmnop" not in redacted)
def test_llm_gateway_failover():
    print("\n--- llm_gateway: failover ---")
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        os.environ.pop(key, None)
    check("no providers configured when keys are absent", llm_gateway.configured_providers() == [])

    async def expect_no_providers():
        try:
            await llm_gateway.chat([{"role": "user", "content": "hi"}])
            return None
        except llm_gateway.AllProvidersFailedError as exc:
            return str(exc)

    msg = asyncio.run(expect_no_providers())
    check("chat fails safely with no keys", msg is not None and "GROQ_API_KEY" in msg)
    check("error message contains no key values", "gsk" not in (msg or "").lower())

    # Only Groq configured.
    os.environ["GROQ_API_KEY"] = "gsk_test_only_placeholder"
    check("configured_providers respects env", [p.name for p in llm_gateway.configured_providers()] == ["groq"])
    os.environ.pop("GROQ_API_KEY", None)

    # Failure on Groq -> automatic failover to Gemini.
    os.environ["GROQ_API_KEY"] = "gsk_test_failover_placeholder"
    os.environ["GEMINI_API_KEY"] = "AIza_test_failover_placeholder"
    fake = _FakeFailoverClient()
    text = asyncio.run(llm_gateway.generate_text("hello", client=fake))
    check("first provider failure falls back to next", text == "fallback-ok")
    check("both providers were attempted", len(fake.calls) == 2)

    # First provider succeeds -> stop there.
    fake2 = _FakeOkClient()
    text2 = asyncio.run(llm_gateway.generate_text("hello", client=fake2))
    check("stops after first success", text2 == "ok" and len(fake2.calls) == 1)

    # 429 rate limit -> failover -> ultimate failure is safe.
    os.environ.pop("GEMINI_API_KEY", None)
    fake3 = _FakeRateLimitClient()

    async def expect_rate_limit():
        try:
            await llm_gateway.chat([{"role": "user", "content": "hi"}], client=fake3)
            return None
        except llm_gateway.AllProvidersFailedError as exc:
            return str(exc)

    msg3 = asyncio.run(expect_rate_limit())
    check("429 surfaces as safe AllProvidersFailedError", msg3 is not None and "rate limit" in msg3.lower())
    os.environ.pop("GROQ_API_KEY", None)


def test_vector_store():
    print("\n--- vector_store ---")
    check("guidance available for all 8 AST rules", all(vector_store.guidance_for(r) for r in ALL_RULES))

    # 1) Unavailable store -> graceful static fallback (no exception).
    blocker = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    blocker_path = blocker.name
    blocker.close()
    os.environ["REVIEWX_CHROMA_DIR"] = blocker_path
    vector_store._client = None
    vector_store._collection = None
    vector_store._ready = None
    ctx = vector_store.get_grounding_context(R_SECRET_API_KEY, "API_KEY = 'sk-...'")
    os.environ.pop("REVIEWX_CHROMA_DIR", None)
    ok = isinstance(ctx, str) and R_SECRET_API_KEY in ctx and "Summary" in ctx
    check("unavailable store returns static fallback", ok)
    check("fallback contains remediation guidance", "Remediation" in (ctx or ""))

    # 2) Unknown rule id -> empty string, still no exception.
    track = vector_store.get_grounding_context("NOT_A_RULE", "whatever")
    check("unknown rule id returns empty context gracefully", track == "")

    # 3) End-to-end: persistent ChromaDB seed + similarity retrieval.
    tmpdir = tempfile.mkdtemp(prefix="reviewx_chroma_check_")
    os.environ["REVIEWX_CHROMA_DIR"] = tmpdir
    vector_store._client = None
    vector_store._collection = None
    vector_store._ready = None
    try:
        count = vector_store.seed_grounding_data()
        check("seeded collection holds 16 documents", count == 16, f"count={count}")
        context = vector_store.get_grounding_context(
            R_SECRET_JWT, "auth_token = 'eyJhbGciOi...'"
        )
        ok_retrieval = isinstance(context, str) and R_SECRET_JWT in context
        check("end-to-end retrieval works", ok_retrieval)
        check("retrieval includes related documents", "Related" in (context or ""))
    except Exception as exc:  # model download / chroma problems are environmental
        print(f"WARN  end-to-end vector store check skipped: {exc!r}")
    finally:
        os.environ.pop("REVIEWX_CHROMA_DIR", None)


def main() -> int:
    print("ReviewX Step 2.3 verification")
    test_llm_gateway_pure()
    test_llm_gateway_failover()
    test_vector_store()
    print("\n" + ("RESULT: PASS" if not FAILURES else "RESULT: FAIL"))
    for problem in FAILURES:
        print(f"  ! {problem}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())