"""Request/response payload schemas for the ReviewX REST API.

The models intentionally mirror the domain shapes defined in the VS Code
extension protocol (``src/types/protocol.ts``) so the REST API can plug into
the existing frontend contract with minimal friction.

Fields are (de)serialized using camelCase aliases by default (e.g.
``languageId``) to match the frontend, while ``snake_case`` Python names
remain valid input via ``populate_by_name=True``.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base model that maps snake_case fields to camelCase JSON."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# ---------------------------------------------------------------------------
# Shared domain models (mirrors src/types/protocol.ts)
# ---------------------------------------------------------------------------


class Position(ApiModel):
    line: int = Field(ge=0, description="0-indexed line number")
    character: int = Field(ge=0, description="0-indexed character position")


class Range(ApiModel):
    start: Position
    end: Position


class DiagnosticItem(ApiModel):
    """A diagnostic finding mapped 1:1 onto ``protocol.ts``.

    ``snippet`` is a REST-side superset: it carries the offending source
    text produced by the AST scanner so the explain endpoint can be fed
    the exact flagged code without re-reading the file.
    """

    id: str
    message: str
    range: Range
    severity: Literal["error", "warning", "information", "hint"] = "information"
    source: Optional[str] = None
    code: Optional[Union[str, int]] = None
    snippet: Optional[str] = None
    related_information: Optional[list[dict[str, Any]]] = None
    category: Optional[str] = None
    recommendation: Optional[str] = None
    title: Optional[str] = None
    uri: Optional[str] = None


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class ScanOptions(ApiModel):
    include_ast: bool = False
    max_diagnostics: int = Field(default=20, ge=1)
    include_workspace_context: bool = False


class ScanRequest(ApiModel):
    uri: Optional[str] = None
    content: Optional[str] = None
    language_id: Optional[str] = None
    options: Optional[ScanOptions] = None


class ScanResponse(ApiModel):
    uri: str
    language_id: str
    line_count: int = 0
    symbols_scanned: int = 0
    findings_count: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    diagnostics: list[DiagnosticItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Explain
# ---------------------------------------------------------------------------


class ExplainRequest(ApiModel):
    uri: Optional[str] = None
    diagnostic_id: Optional[str] = None
    rule_id: Optional[str] = None
    language_id: Optional[str] = None
    snippet: Optional[str] = None


class ExplainResponse(ApiModel):
    explanation: str
    steps: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


class VerifyRequest(ApiModel):
    question_id: str
    challenge_id: Optional[str] = None
    selected_option_id: Optional[str] = None
    text_answer: Optional[str] = None
    code_snippet: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class VerifyResponse(ApiModel):
    """Evaluation of a developer's comprehension answer.

    Mirrors ``VerifyAnswerResult`` in ``src/types/protocol.ts``.
    ``is_correct`` / ``score`` are ``None`` when the answer could not be
    evaluated (for example when no LLM provider is configured).
    """

    question_id: str
    is_correct: Optional[bool] = None
    score: Optional[float] = Field(default=None, ge=0, le=100)
    feedback: str
    explanation: Optional[str] = None
    hints: list[str] = Field(default_factory=list)
    next_challenge_id: Optional[str] = None
    timestamp: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        description="Unix epoch milliseconds",
    )
