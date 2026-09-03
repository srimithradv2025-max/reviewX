"""Smoke test for Step 2.4 — REST endpoints wired to the services.

Run (PowerShell):
    Set-Location c:\\Users\\rindh\\reviewX\\backend
    .\\venv\\Scripts\\python.exe tests\\run_step2_4_check.py

The test temporarily clears the LLM API-key environment variables and points
the vector store at an invalid ChromaDB path so the explain/verify
GRACEFUL-DEGRADATION paths (static guidance / unscored result) run
deterministically offline — no provider, network, or model download needed.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(r"c:\Users\rindh\reviewX\backend")
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import vector_store  # noqa: E402
from app.services.ast_parser import (  # noqa: E402
    R_DANGEROUS_EVAL,
    R_SECRET_API_KEY,
    R_SECRET_JWT,
)

_LLM_KEYS = ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY")
_FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"{status}  {name}{suffix}")
    if not condition:
        _FAILURES.append(name)


SAMPLE_VULNERABLE = '''
import os


def deploy() -> str:
    api_key = "sk-live-1234567890abcdef1234567890abcdef"
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    code = input("paste code: ")
    eval(code)
    return api_key
'''


def test_health(client: TestClient) -> None:
    print("\n--- GET /health ---")
    response = client.get("/health")
    check(
        "health returns ok",
        response.status_code == 200 and response.json() == {"status": "ok"},
        f"status={response.status_code}",
    )


def test_scan(client: TestClient) -> None:
    print("\n--- POST /api/v1/scan ---")
    payload = {"uri": "snippet.py", "content": SAMPLE_VULNERABLE, "languageId": "python"}
    response = client.post("/api/v1/scan", json=payload)
    body = response.json()
    check("scan returns 200", response.status_code == 200, f"status={response.status_code}")
    envelope = ("uri", "languageId", "lineCount", "findingsCount", "timestamp", "diagnostics")
    check("scan camelCase envelope", all(key in body for key in envelope), f"keys={sorted(body)}")
    check("uri echoed", body.get("uri") == "snippet.py")
    check("languageId echoed", body.get("languageId") == "python")
    check("lineCount > 0", (body.get("lineCount") or 0) >= 8, f"lineCount={body.get('lineCount')}")

    diagnostics = body.get("diagnostics") or []
    rule_ids = {diag.get("id") for diag in diagnostics}
    check("hardcoded API key detected", R_SECRET_API_KEY in rule_ids, f"ids={sorted(rule_ids)}")
    check("hardcoded JWT detected", R_SECRET_JWT in rule_ids, f"ids={sorted(rule_ids)}")
    check("eval() detected", R_DANGEROUS_EVAL in rule_ids, f"ids={sorted(rule_ids)}")
    check("findingsCount matches diagnostics", body.get("findingsCount") == len(diagnostics))

    api_diag = next((d for d in diagnostics if d.get("id") == R_SECRET_API_KEY), None)
    check(
        "severity high->error",
        api_diag is not None and api_diag.get("severity") == "error",
        f"diag={api_diag}",
    )
    check(
        "diagnostic line is 0-indexed",
        api_diag is not None
        and api_diag["range"]["start"]["line"] == api_diag["range"]["end"]["line"]
        and api_diag["range"]["start"]["line"] >= 0,
        f"range={api_diag and api_diag.get('range')}",
    )
    check(
        "diagnostic carries offending snippet",
        api_diag is not None and bool(api_diag.get("snippet")),
        f"snippet={api_diag and api_diag.get('snippet')}",
    )

    capped = client.post(
        "/api/v1/scan",
        json={**payload, "options": {"maxDiagnostics": 2}},
    )
    capped_count = len((capped.json().get("diagnostics") or []))
    check("maxDiagnostics cap respected", capped_count == 2, f"count={capped_count}")

    bad = client.post("/api/v1/scan", json={})
    check("scan without content/uri -> 422", bad.status_code == 422)


def test_explain(client: TestClient) -> None:
    print("\n--- POST /api/v1/explain ---")
    response = client.post(
        "/api/v1/explain",
        json={
            "ruleId": R_SECRET_API_KEY,
            "uri": "snippet.py",
            "languageId": "python",
            "snippet": 'api_key = "sk-live-..."',
        },
    )
    body = response.json()
    check("explain returns 200", response.status_code == 200, f"status={response.status_code}")
    explanation = body.get("explanation") or ""
    check(
        "explanation is a non-empty string",
        isinstance(explanation, str) and len(explanation) > 30,
        f"len={len(explanation)}",
    )
    check(
        "explanation references the rule",
        R_SECRET_API_KEY in explanation,
        f"= {explanation[:80]!r}...",
    )
    check(
        "steps is a non-empty list",
        isinstance(body.get("steps"), list) and len(body.get("steps") or []) > 0,
    )

    missing = client.post("/api/v1/explain", json={})
    check("explain without ruleId -> 422", missing.status_code == 422)


def test_verify(client: TestClient) -> None:
    print("\n--- POST /api/v1/verify ---")
    response = client.post(
        "/api/v1/verify",
        json={
            "questionId": "q-1",
            "challengeId": "challenge-7",
            "textAnswer": "Because eval() executes arbitrary code.",
            "codeSnippet": "eval(code)",
        },
    )
    body = response.json()
    check("verify returns 200", response.status_code == 200, f"status={response.status_code}")
    envelope = ("questionId", "isCorrect", "feedback", "timestamp")
    check("verify camelCase envelope", all(key in body for key in envelope), f"keys={sorted(body)}")
    check("questionId echoed", body.get("questionId") == "q-1")
    check(
        "isCorrect is bool or null",
        body.get("isCorrect") is None or isinstance(body.get("isCorrect"), bool),
        f"isCorrect={body.get('isCorrect')!r}",
    )
    check(
        "feedback is a non-empty string",
        isinstance(body.get("feedback"), str) and len(body.get("feedback") or "") > 0,
    )
    check(
        "timestamp is epoch-ms int",
        isinstance(body.get("timestamp"), int) and body.get("timestamp", 0) > 0,
        f"timestamp={body.get('timestamp')!r}",
    )
    check(
        "nextChallengeId increments 7->8",
        body.get("nextChallengeId") == "challenge-8",
        f"next={body.get('nextChallengeId')!r}",
    )


def main() -> int:
    saved_keys = {key: os.environ.get(key) for key in _LLM_KEYS}
    for key in _LLM_KEYS:
        os.environ.pop(key, None)

    # Point the vector store at an invalid path so grounding always uses the
    # built-in static fallback (no ChromaDB or model download in the smoke test).
    blocker = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    blocker_path = blocker.name
    blocker.close()
    os.environ["REVIEWX_CHROMA_DIR"] = blocker_path
    vector_store._client = None
    vector_store._collection = None
    vector_store._ready = None

    print("ReviewX Step 2.4 smoke test (REST endpoints wired to services)")
    client = TestClient(app)
    try:
        test_health(client)
        test_scan(client)
        test_explain(client)
        test_verify(client)
    finally:
        for key, value in saved_keys.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
        os.environ.pop("REVIEWX_CHROMA_DIR", None)
        try:
            os.remove(blocker_path)
        except OSError:
            pass

    print("\n" + ("RESULT: PASS" if not _FAILURES else "RESULT: FAIL"))
    for problem in _FAILURES:
        print(f"  ! {problem}")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())