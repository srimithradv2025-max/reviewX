"""REST API endpoints for ReviewX (Step 2.4 — services wired into the API).

The AST scanner, grounding vector store, and async LLM gateway are now
hooked up to the REST layer. LLM-dependent endpoints degrade gracefully to
trusted static guidance / an unscored result when no provider is configured,
so the API keeps answering in a local, key-less environment.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException

from app.schemas.payload import (
    DiagnosticItem,
    ExplainRequest,
    ExplainResponse,
    Position,
    Range,
    ScanOptions,
    ScanRequest,
    ScanResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services import ast_parser, llm_gateway, vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["reviewx"])

_URI_UNKNOWN = "unknown:file"
_LANGUAGE_PLAINTEXT = "plaintext"

# AST scanner severities (high/medium/low) -> VS Code diagnostic severities.
_SEVERITY_TO_VSCODE: dict[str, str] = {
    ast_parser.SEVERITY_HIGH: "error",
    ast_parser.SEVERITY_MEDIUM: "warning",
    ast_parser.SEVERITY_LOW: "information",
}

_EXPLAIN_SYSTEM_PROMPT = (
    "You are ReviewX, a senior Python security reviewer. Given a code "
    "vulnerability finding and trusted grounding context, explain to a "
    "developer (1) what the problem is, (2) why it is dangerous, and "
    "(3) how to fix it. Be specific, concise, and reference the snippet."
)

_VERIFY_SYSTEM_PROMPT = (
    "You are ReviewX, verifying a developer's comprehension answer. Judge "
    "correctness strictly against the reference answer. Reply with ONLY "
    "valid JSON: {\"isCorrect\": true|false, \"score\": 0-100, "
    "\"feedback\": \"...\", \"explanation\": \"...\", \"hints\": [...]}"
)


def _is_python(language_id: Optional[str]) -> bool:
    """True when a language id selects the (only) supported AST scanner."""
    if not language_id:
        return True
    return language_id.strip().lower() in ("python", "py")


def _to_diagnostic(finding: ast_parser.Finding, uri: str) -> DiagnosticItem:
    """Map an AST ``Finding`` onto the frontend ``DiagnosticItem`` shape.

    The AST scanner reports 1-based lines; the protocol uses 0-indexed
    lines, so the line number is decremented before mapping.
    """
    line = max(int(finding.line) - 1, 0)
    guidance = vector_store.guidance_for(finding.rule_id)
    return DiagnosticItem(
        id=finding.rule_id,
        message=finding.message,
        range=Range(
            start=Position(line=line, character=0),
            end=Position(line=line, character=0),
        ),
        severity=_SEVERITY_TO_VSCODE.get(finding.severity, "information"),
        source="reviewx",
        code=finding.rule_id,
        title=guidance.get("title") if guidance else None,
        recommendation=guidance.get("remediation") if guidance else None,
        snippet=finding.snippet,
        uri=uri,
    )


def _read_file(uri: str) -> str:
    """Read UTF-8 file content from a plain path or a ``file://`` URI."""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        raw_path = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:", raw_path):  # file:///C:/... on Windows
            raw_path = raw_path[1:]
        path = Path(raw_path)
    else:
        path = Path(uri)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=404 if isinstance(exc, FileNotFoundError) else 422,
            detail=f"Could not read '{uri}': {exc.__class__.__name__}.",
        ) from exc


def _next_challenge_id(challenge_id: Optional[str]) -> Optional[str]:
    """Suggest the next challenge id by incrementing a trailing integer."""
    if not challenge_id:
        return None
    match = re.search(r"^(.*?)(\d+)$", challenge_id)
    if not match:
        return f"{challenge_id}-next"
    return f"{match.group(1)}{int(match.group(2)) + 1}"


def _static_explanation(rule_id: str, snippet: str, context: str) -> str:
    """Deterministic, LLM-free explanation built from the grounding data."""
    if context:
        return context
    guidance = vector_store.guidance_for(rule_id) or {}
    title = guidance.get("title") or rule_id
    text = f"{title}: this code was flagged by the ReviewX rule '{rule_id}'."
    if snippet:
        text += f"\nSnippet: {snippet}"
    return text


def _explanation_steps() -> list[str]:
    return [
        "Confirm which code triggered the rule.",
        "Understand why the pattern is unsafe.",
        "Apply the recommended remediation from the grounding context.",
    ]


def _verify_prompt(request: VerifyRequest) -> str:
    lines = [f"Question id: {request.question_id}"]
    if request.challenge_id:
        lines.append(f"Challenge id: {request.challenge_id}")
    if request.selected_option_id:
        lines.append(f"Selected option id: {request.selected_option_id}")
    if request.text_answer:
        lines.append(f"Developer's answer:\n{request.text_answer}")
    if request.code_snippet:
        lines.append(f"Code snippet:\n```\n{request.code_snippet}\n```")
    if request.metadata:
        lines.append(f"Metadata: {request.metadata}")
    return "\n".join(lines)


def _parse_verdict(text: str) -> Optional[dict[str, Any]]:
    """Best-effort extraction of the model's JSON verdict from the reply."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _build_verdict_response(
    request: VerifyRequest,
    data: dict[str, Any],
) -> VerifyResponse:
    is_correct = bool(data.get("isCorrect", data.get("is_correct", False)))
    try:
        score = max(0.0, min(100.0, float(data.get("score"))))
    except (TypeError, ValueError):
        score = 100.0 if is_correct else 0.0
    raw_hints = data.get("hints") or []
    hints = [str(hint) for hint in raw_hints] if isinstance(raw_hints, list) else []
    feedback = str(
        data.get("feedback") or ("Correct answer." if is_correct else "Incorrect answer.")
    )
    explanation = str(data.get("explanation") or "") or None
    return VerifyResponse(
        question_id=request.question_id,
        is_correct=is_correct,
        score=score,
        feedback=feedback,
        explanation=explanation,
        hints=hints,
        next_challenge_id=_next_challenge_id(request.challenge_id),
        timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
    )


@router.post("/scan", response_model=ScanResponse)
async def scan(request: ScanRequest) -> ScanResponse:
    """Scan Python source delivered as raw ``content`` or a file ``uri``."""
    if request.content is None and request.uri is None:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'content' or 'uri' to scan.",
        )

    content = request.content
    line_count = 0
    if content is not None:
        line_count = content.count("\n") + 1
    elif request.uri is not None:
        content = _read_file(request.uri)
        line_count = content.count("\n") + 1

    options = request.options or ScanOptions()
    uri = request.uri or _URI_UNKNOWN

    diagnostics: list[DiagnosticItem] = []
    if _is_python(request.language_id):
        findings = ast_parser.scan_python(content or "")
        diagnostics = [
            _to_diagnostic(finding, uri) for finding in findings
        ][: options.max_diagnostics]

    return ScanResponse(
        uri=uri,
        language_id=request.language_id or _LANGUAGE_PLAINTEXT,
        line_count=line_count,
        symbols_scanned=0,
        findings_count=len(diagnostics),
        timestamp=datetime.now(timezone.utc),
        diagnostics=diagnostics,
    )


@router.post("/explain", response_model=ExplainResponse)
async def explain(request: ExplainRequest) -> ExplainResponse:
    """Explain a finding using trusted grounding plus the LLM (when available)."""
    rule_id = request.rule_id or request.diagnostic_id
    if not rule_id:
        raise HTTPException(
            status_code=422,
            detail="Provide 'ruleId' (or 'diagnosticId') to explain.",
        )

    snippet = (request.snippet or "").strip()
    context = vector_store.get_grounding_context(rule_id, snippet)

    prompt_lines = [f"Finding rule: {rule_id}"]
    if request.uri:
        prompt_lines.append(f"File: {request.uri}")
    if snippet:
        prompt_lines.append(f"Offending snippet:\n```python\n{snippet}\n```")
    prompt_lines.append(f"Trusted grounding context:\n{context}")

    try:
        explanation = (
            await llm_gateway.generate_text(
                "\n".join(prompt_lines),
                system=_EXPLAIN_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=600,
            )
        ).strip()
    except llm_gateway.AllProvidersFailedError as exc:
        logger.warning("LLM unavailable for /explain; using static guidance: %s", exc)
        explanation = _static_explanation(rule_id, snippet, context)

    return ExplainResponse(
        explanation=explanation,
        steps=_explanation_steps(),
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify(request: VerifyRequest) -> VerifyResponse:
    """Evaluate a comprehension answer with the LLM.

    Without a configured provider the endpoint still answers 200 with an
    unscored result (``isCorrect``/``score`` null) and honest feedback.
    """
    try:
        judge_text = (
            await llm_gateway.generate_text(
                _verify_prompt(request),
                system=_VERIFY_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=400,
            )
        ).strip()
        verdict = _parse_verdict(judge_text)
    except llm_gateway.AllProvidersFailedError as exc:
        logger.warning("LLM unavailable for /verify; answer not evaluated: %s", exc)
        verdict = None

    if verdict is None:
        return VerifyResponse(
            question_id=request.question_id,
            is_correct=None,
            score=None,
            feedback=(
                "Answer verification requires a configured LLM provider "
                "(GROQ_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY); "
                "the answer was not scored."
            ),
            next_challenge_id=_next_challenge_id(request.challenge_id),
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
        )

    return _build_verdict_response(request, verdict)
