"""AST-based static analysis scanner for ReviewX.

Uses Python's **built-in** ``ast`` module (no third-party dependencies) to
detect common security issues in Python source code:

1. Hardcoded secrets             -> ``SECRET_API_KEY``, ``SECRET_JWT``,
                                    ``SECRET_PASSWORD``, ``SECRET_CONNECTION_STRING``
2. Dynamic code execution        -> ``DANGEROUS_EVAL``, ``DANGEROUS_EXEC``
3. SQL built by interpolation    -> ``UNSAFE_SQL``
4. Missing safety interlocks     -> ``MISSING_SAFETY_INTERLOC``

Every finding carries a ``rule_id``, ``line`` (1-based, straight from the AST),
``severity``, a human-readable ``message`` and the offending ``snippet``.

The public entry points are ``scan_python()`` and ``scan_file()``.  They are kept
deliberately dependency-free so the scanner can be wired into the REST endpoint
later without importing FastAPI/pydantic models.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Sequence, Union

# -----------------------------------------------------------------------------
# Finding model
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """A single security finding produced by the AST scanner."""

    rule_id: str
    line: int  # 1-based line number straight from the AST
    severity: str  # "high" | "medium" | "low"
    message: str
    snippet: str


# -----------------------------------------------------------------------------
# Rule-ID constants
# -----------------------------------------------------------------------------

R_SECRET_API_KEY = "SECRET_API_KEY"
R_SECRET_JWT = "SECRET_JWT"
R_SECRET_PASSWORD = "SECRET_PASSWORD"
R_SECRET_CONNECTION_STRING = "SECRET_CONNECTION_STRING"
R_DANGEROUS_EVAL = "DANGEROUS_EVAL"
R_DANGEROUS_EXEC = "DANGEROUS_EXEC"
R_UNSAFE_SQL = "UNSAFE_SQL"
R_MISSING_SAFETY_INTERLOC = "MISSING_SAFETY_INTERLOC"

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Snippet length cap so a single finding never drags huge literals around.
_MAX_SNIPPET_CHARS = 160

# -----------------------------------------------------------------------------
# Secret detection helpers
# -----------------------------------------------------------------------------

# Substrings that mark a value as a placeholder/example rather than a real
# secret.  Kept conservative so genuine secrets are never hidden by it.
_PLACEHOLDER_TOKENS = (
    "your_",
    "your-",
    "xxx",
    "example",
    "changeme",
    "todo",
    "sample",
    "placeholder",
    "dummy",
    "****",
    "######",
    "your api",
    "your-api",
)
def _is_placeholder(value: str) -> bool:
    """True when ``value`` looks like a docs/example placeholder, not a secret."""
    if len(value.strip()) < 6:
        return True
    lower = value.lower()
    return any(token in lower for token in _PLACEHOLDER_TOKENS)


def _is_strong_secret(value: str) -> bool:
    """True when ``value`` is long enough to plausibly be a generated secret."""
    return len(value) >= 16 and not _is_placeholder(value)


# --- Token value fingerprints (the actual secret shapes) ----------------------

_JWT_DOTTED_RE = re.compile(
    r"^eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{2,}$"
)
_AWS_ACCESS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_OPENAI_API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
_GITHUB_TOKEN_RE = re.compile(
    r"\b(?:ghp_|github_pat_|github_oauth_)[A-Za-z0-9_-]{20,}\b"
)
_SLACK_TOKEN_RE = re.compile(r"\bxox[aboprs]-[A-Za-z0-9-]{10,}\b")
_STRIPE_TOKEN_RE = re.compile(r"\b(?:sk|pk)_(?:test_)?live_[A-Za-z0-9]{10,}\b", re.I)
_SENDGRID_TOKEN_RE = re.compile(r"\bSG\.[A-Za-z0-9_-]{20,}\b")
_GOOGLE_SERVICE_ACCOUNT_RE = re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OpenSSH )?PRIVATE KEY-----"
)


def _looks_like_jwt(value: str, name: str) -> bool:
    """JWT detection: the classic 3-segment ``eyJ...`` shape or a ``*_jwt`` name."""
    if _JWT_DOTTED_RE.match(value):
        return True
    return "jwt" in name.lower() and _is_strong_secret(value) and "." in value


def _looks_like_api_key(value: str, name: str) -> bool:
    """Per-provider fingerprints are the most reliable API-key signals."""
    if _AWS_ACCESS_KEY_RE.search(value):
        return True
    if _OPENAI_API_KEY_RE.search(value):
        return True
    if _GITHUB_TOKEN_RE.search(value):
        return True
    if _SLACK_TOKEN_RE.search(value):
        return True
    if _STRIPE_TOKEN_RE.search(value):
        return True
    if _SENDGRID_TOKEN_RE.search(value):
        return True
    if _GOOGLE_SERVICE_ACCOUNT_RE.search(value):
        return True
    if _PRIVATE_KEY_RE.search(value):
        return True
    # Fall back to the variable name: anything offered as a key/token/secret
    # with a long enough value is worth reporting as an API key.
    n = name.lower()
    return _is_strong_secret(value) and (
        "key" in n or "secret" in n or "token" in n or n in ("sk", "api")
    )
# --- Connection-string fingerprints -------------------------------------------

# scheme://user:password@host  (only true DB schemes that can carry credentials)
_DB_URL_WITH_CREDENTIALS_RE = re.compile(
    r"(?i)(?:"
    r"mysql|mariadb|postgres|postgresql|mongodb|mongodb\+srv|redis|rediss|"
    r"oracle|snowflake|sqlserver|amqp|jdbc:mysql|jdbc:postgresql"
    r")://[^@\s/]+:[^@\s]+@"
)
# ODBC-style DSN:  Server=...;...;Password=...  (semicolon separated settings)
_ODBC_HOST_RE = re.compile(
    r"(?i)(?:server|data[ _]source|host)\s*=\s*[^;\s]{1,40}(?:;|$)"
)
_ODBC_PASSWORD_RE = re.compile(r"(?i)(?:pwd|password)\s*=")


def _is_connection_string(value: str) -> bool:
    """True when a literal looks like a DB URL/DSN that embeds credentials."""
    if _DB_URL_WITH_CREDENTIALS_RE.search(value):
        return True
    if _ODBC_HOST_RE.search(value) and _ODBC_PASSWORD_RE.search(value):
        return True
    return False


# Password heuristics are purely name-driven (see _classify_secret_value below).

# Variable/dict-key names that always mean "sensitive material lives here".
_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "auth_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "private_key",
}


def _classify_secret_value(name: str, value: str) -> Optional[str]:
    """Return the rule ID for a (name, value) secret pair, else ``None``.

    Order matters: JWTs and obvious API-key fingerprints are strongest; a
    password-named variable wins over the generic key/token fallback.
    """
    if _looks_like_jwt(value, name):
        return R_SECRET_JWT
    n = name.lower()
    is_password_name = (
        "password" in n
        or "passwd" in n
        or n == "pwd"
        or n.endswith("_pwd")
        or n.endswith("_pass")
    )
    if is_password_name:
        return R_SECRET_PASSWORD if not _is_placeholder(value) else None
    if _is_connection_string(value):
        return R_SECRET_CONNECTION_STRING
    if _looks_like_api_key(value, name):
        return R_SECRET_API_KEY
    return None


def _mask_secret(value: str) -> str:
    """Short masked preview for messages, e.g. ``sk-abcd...yz``."""
    if len(value) <= 8:
        return f"'{value}'"
    return f"'{value[:5]}...{value[-2:]}'"


def _string_literal(node: ast.AST) -> Optional[str]:
    """Return the raw string when ``node`` is a plain string literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None
# -----------------------------------------------------------------------------
# Generic AST helpers shared by the visitors
# -----------------------------------------------------------------------------


def _call_dotted_name(node: ast.Call) -> Optional[str]:
    """Best-effort dotted name for a call, e.g. ``os.path.join`` / ``builtins.eval``."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = []
        cur = func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        # Include the receiver name when it is a plain Name; otherwise return
        # the bare attribute chain (e.g. "format" for  "x".format(...)).
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _iter_assigned_names(target: ast.AST) -> Iterator[str]:
    """Yield every bound variable name for an assignment target."""
    for child in ast.walk(target):
        if isinstance(child, ast.Name):
            yield child.id


def _snippet(source: str, node: ast.AST, lines: Sequence[str]) -> str:
    """Extract the exact source segment for ``node``, falling back to the line."""
    try:
        segment = ast.get_source_segment(source, node)
    except (ValueError, TypeError):
        segment = None
    if not segment:
        line_no = getattr(node, "lineno", None)
        if line_no and 1 <= line_no <= len(lines):
            segment = lines[line_no - 1]
    cleaned = (segment or "").replace("\r", " ").replace("\n", " ").strip()
    if len(cleaned) > _MAX_SNIPPET_CHARS:
        cleaned = cleaned[:_MAX_SNIPPET_CHARS] + "..."
    return cleaned
# -----------------------------------------------------------------------------
# SQL construction detection
# -----------------------------------------------------------------------------

_SQL_KEYWORDS = {
    "select",
    "insert",
    "update",
    "delete",
    "drop",
    "create",
    "alter",
    "truncate",
    "replace",
    "from",
    "where",
    "join",
    "into",
    "table",
    "set",
}


def _contains_sql(text: str) -> bool:
    """Heuristic: True when a string fragment looks like SQL rather than prose.

    Requiring 2+ keywords (e.g. SELECT + FROM) or a leading SQL verb keeps
    obvious false positives (``"Please select a file"``) out of the results.
    """
    lower = text.lower()
    hits = [
        kw for kw in _SQL_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", lower)
    ]
    if len(hits) >= 2:
        return True
    if re.match(r"\s*(select|insert|update|delete|drop|create|alter)\b", lower):
        return True
    return False


def _joined_str_static_text(node: ast.JoinedStr) -> str:
    """Static (non-interpolated) text inside an f-string."""
    parts: list[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            parts.append(part.value)
    return "".join(parts)


def _is_dynamic(expr: ast.AST) -> bool:
    """True when ``expr`` is anything other than a plain string literal.

    Used to let safe, entirely-static SQL strings pass while flagging the
    moment a variable, call, subscript or f-string value appears.
    """
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return False
    if isinstance(expr, ast.JoinedStr):
        return any(isinstance(sp, ast.FormattedValue) for sp in expr.values)
    if isinstance(expr, ast.BinOp):
        return _is_dynamic(expr.left) or _is_dynamic(expr.right)
    return True


def _static_text(expr: ast.AST) -> str:
    """Flatten a ``+`` chain of string literals into one joined string."""
    parts: list[str] = []
    stack: list[ast.AST] = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.BinOp) and node.op.__class__.__name__ == "Add":
            stack.append(node.left)
            stack.append(node.right)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            parts.append(_joined_str_static_text(node))
    return "".join(parts)
# -----------------------------------------------------------------------------
# Main AST visitor
# -----------------------------------------------------------------------------


class _ScanVisitor(ast.NodeVisitor):
    """Walks a parsed module once and collects every finding."""

    def __init__(self, source, lines, parents):
        self.source = source
        self.lines = lines
        self.parents = parents
        self.findings: list[Finding] = []

    # -- result helper -------------------------------------------------------

    def _add(self, rule_id, node, severity, message):
        """Append a single Finding for the given AST node."""
        self.findings.append(
            Finding(
                rule_id=rule_id,
                line=node.lineno,
                severity=severity,
                message=message,
                snippet=_snippet(self.source, node, self.lines),
            )
        )

    # -- secret reporting ----------------------------------------------------

    def _generic_secret_check(self, name, value, node) -> None:
        """Classify ``(name, value)`` and emit the matching secret finding."""
        rule = _classify_secret_value(name, value)
        if rule is None:
            return
        masked = _mask_secret(value)
        if rule == R_SECRET_JWT:
            self._add(
                R_SECRET_JWT,
                node,
                SEVERITY_HIGH,
                f"Hardcoded JWT/token in '{name}': {masked}; rotate it now and "
                "load from env/secret store instead.",
            )
        elif rule == R_SECRET_PASSWORD:
            self._add(
                R_SECRET_PASSWORD,
                node,
                SEVERITY_HIGH,
                f"Hardcoded password in '{name}': {masked}; use a secret store "
                "and hashed/auth'd credentials.",
            )
        elif rule == R_SECRET_CONNECTION_STRING:
            self._add(
                R_SECRET_CONNECTION_STRING,
                node,
                SEVERITY_HIGH,
                f"Connection string in '{name}' embeds credentials; externalize "
                "the DSN via env/config.",
            )
        else:  # SECRET_API_KEY
            self._add(
                R_SECRET_API_KEY,
                node,
                SEVERITY_HIGH,
                f"Hardcoded API key in '{name}': {masked}; rotate it and load "
                "from env/config.",
            )

    def _check_value_only(self, value, node) -> None:
        """Emit findings for value-shaped secrets that need no variable name."""
        if _is_placeholder(value):
            return
        if _is_connection_string(value):
            self._add(
                R_SECRET_CONNECTION_STRING,
                node,
                SEVERITY_HIGH,
                f"Connection string embeds credentials: {_mask_secret(value)}; "
                "externalize via env/config.",
            )
            return
        if _JWT_DOTTED_RE.match(value):
            self._add(
                R_SECRET_JWT,
                node,
                SEVERITY_HIGH,
                f"Hardcoded JWT literal: {_mask_secret(value)}; rotate it now.",
            )
            return
        if _looks_like_api_key(value, ""):
            self._add(
                R_SECRET_API_KEY,
                node,
                SEVERITY_HIGH,
                f"Hardcoded API key literal: {_mask_secret(value)}; rotate it now.",
            )

    # -- assignments / literals that can hold secrets -------------------------

    def visit_Assign(self, node) -> None:
        value = _string_literal(node.value)
        if value is not None:
            for target in node.targets:
                for name in _iter_assigned_names(target):
                    self._generic_secret_check(name, value, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node) -> None:
        if node.value is not None:
            value = _string_literal(node.value)
            if value is not None and isinstance(node.target, ast.Name):
                self._generic_secret_check(node.target.id, value, node)
        self.generic_visit(node)

    def visit_Dict(self, node) -> None:
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                key_lower = key.value.lower()
                literal = _string_literal(value)
                if literal is not None and key_lower in _SENSITIVE_KEYS:
                    self._generic_secret_check(key_lower, literal, node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node) -> None:
        self._check_function_defaults(node)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _check_function_defaults(self, node) -> None:
        """Secrets as default argument values, e.g. ``def f(password="x")``."""
        args = node.args
        offset = len(args.args) - len(args.defaults)
        for index, default in enumerate(args.defaults):
            literal = _string_literal(default)
            arg_index = offset + index
            if literal is not None and arg_index < len(args.args):
                self._generic_secret_check(args.args[arg_index].arg, literal, node)
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            if default is not None:
                literal = _string_literal(default)
                if literal is not None:
                    self._generic_secret_check(arg.arg, literal, node)

    def visit_Return(self, node) -> None:
        if node.value is not None:
            literal = _string_literal(node.value)
            if literal is not None:
                self._check_value_only(literal, node)
        self.generic_visit(node)
# -- dangerous dynamic execution & call-site secrets ------------------------

    def visit_Call(self, node) -> None:
        name = _call_dotted_name(node) or ""
        base = name.split(".")[-1]

        # 1) eval() / exec()  (plain or explicitly builtins-qualified)
        if name in ("eval", "builtins.eval"):
            self._add(
                R_DANGEROUS_EVAL,
                node,
                SEVERITY_HIGH,
                "eval() executes arbitrary code; avoid it or strictly validate input.",
            )
        elif name in ("exec", "builtins.exec"):
            self._add(
                R_DANGEROUS_EXEC,
                node,
                SEVERITY_HIGH,
                "exec() executes arbitrary code; avoid it or strictly validate input.",
            )

        # 2) secret values passed as keyword args, e.g. connect(password="...")
        for kw in node.keywords:
            if kw.arg and kw.arg.lower() in _SENSITIVE_KEYS:
                literal = _string_literal(kw.value)
                if literal is not None:
                    self._generic_secret_check(kw.arg, literal, node)

        # 3) connection strings passed directly to a positional argument
        for arg in node.args:
            literal = _string_literal(arg)
            if literal is not None and _is_connection_string(literal):
                self._add(
                    R_SECRET_CONNECTION_STRING,
                    node,
                    SEVERITY_HIGH,
                    f"Connection string passed inline embeds credentials: "
                    f"{_mask_secret(literal)}; externalize via env/config.",
                )

        # 4) SQL assembled with str.format(...)
        if base == "format" and isinstance(node.func, ast.Attribute):
            static = _static_text(node.func.value)
            if (node.args or node.keywords) and _contains_sql(static):
                self._add(
                    R_UNSAFE_SQL,
                    node,
                    SEVERITY_HIGH,
                    "SQL built with str.format() interpolation; use parameterized "
                    "queries with placeholders.",
                )

        # 5) destructive filesystem operation without a confirmation guard
        destructive = _destructive_op_name(node)
        if destructive is not None and self._missing_destructive_guard(node):
            self._add(
                R_MISSING_SAFETY_INTERLOC,
                node,
                SEVERITY_MEDIUM,
                f"'{destructive}' is a destructive filesystem operation with no "
                "visible confirmation/safety guard (e.g. force/confirm/input check).",
            )

        # 6) thread lock acquired but never released in the same function
        if base == "acquire" and not self._has_release_or_with(node):
            self._add(
                R_MISSING_SAFETY_INTERLOC,
                node,
                SEVERITY_MEDIUM,
                "Lock acquired without a matching release/interlock in this "
                "function; use 'with lock:' or ensure release() in all paths.",
            )

        self.generic_visit(node)
# -- unsafe SQL built via f-strings / concatenation / % formatting --------

    def visit_JoinedStr(self, node) -> None:
        if any(isinstance(part, ast.FormattedValue) for part in node.values):
            static = _joined_str_static_text(node)
            if _contains_sql(static):
                self._add(
                    R_UNSAFE_SQL,
                    node,
                    SEVERITY_HIGH,
                    "SQL query built with f-string interpolation; use parameterized "
                    "queries to prevent SQL injection.",
                )
        self.generic_visit(node)

    def visit_BinOp(self, node) -> None:
        # "...SQL..." + user_variable
        if node.op.__class__.__name__ == "Add":
            static = _static_text(node)
            if _contains_sql(static) and _is_dynamic(node):
                self._add(
                    R_UNSAFE_SQL,
                    node,
                    SEVERITY_HIGH,
                    "SQL query built with string concatenation; use parameterized "
                    "queries to prevent SQL injection.",
                )
        # "...SQL... %s" % user_input
        elif node.op.__class__.__name__ == "Mod":
            left_static = _static_text(node.left)
            if _contains_sql(left_static):
                self._add(
                    R_UNSAFE_SQL,
                    node,
                    SEVERITY_HIGH,
                    "SQL query built with %-formatting; %s style interpolation is "
                    "not parameterization and can enable SQL injection.",
                )
        self.generic_visit(node)

    # -- safety-interlock helpers ---------------------------------------------

    def _missing_destructive_guard(self, node) -> bool:
        """True when a destructive call has no visible confirmation interlock."""
        current = node
        while current in self.parents:
            parent = self.parents[current]
            if isinstance(parent, ast.If):
                condition = ast.get_source_segment(self.source, parent.test) or ""
                if _INTERLOCK_CONDITION_RE.search(condition):
                    return False  # guarded by an if/input check
            elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Fallback: any interactive confirmation anywhere in the function.
                src = ast.get_source_segment(self.source, parent) or ""
                if _INTERLOCK_BODY_RE.search(src):
                    return False
                break
            current = parent
        return True

    def _has_release_or_with(self, node) -> bool:
        """True when the enclosing function releases the lock or uses ``with``."""
        base = _call_dotted_name(node) or ""
        base_var = base[: -len(".acquire")] if base.endswith(".acquire") else "lock"
        current = node
        enclosing = None
        while current in self.parents:
            parent = self.parents[current]
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                enclosing = parent
                break
            current = parent
        body = list(ast.walk(enclosing)) if enclosing is not None else [node]
        release_name = f"{base_var}.release"
        for candidate in body:
            if isinstance(candidate, ast.Call):
                if (_call_dotted_name(candidate) or "") == release_name:
                    return True
            elif isinstance(candidate, ast.With):
                ctx = (
                    candidate.items[0].context_expr if candidate.items else None
                )
                if isinstance(ctx, ast.Name) and ctx.id == base_var:
                    return True
        return False
# -----------------------------------------------------------------------------
# Destructive filesystem operation detection
# -----------------------------------------------------------------------------

# Guard words that signal a deliberate confirmation/safety interlock.
_INTERLOCK_CONDITION_RE = re.compile(
    r"(?i)(confirm|force|proceed|sure|really|dry[_ -]?run|input\s*\(|are you sure)"
)
_INTERLOCK_BODY_RE = re.compile(
    r"(?i)\binput\s*\([^)]*(?:sure|confirm|delete|remove|proceed|really|y/n)"
)

# Suffixes that are nearly always filesystem-destructive and rarely used on
# ordinary container objects (unlike e.g. ``list.remove``).
_DESTRUCTIVE_FS_BASES = {"rmtree", "rmdir", "unlink", "rmoveat", "replace"}


def _destructive_op_name(node: ast.Call) -> Optional[str]:
    """Return the dotted call name when ``node`` looks like a destructive FS op."""
    name = _call_dotted_name(node)
    if not name:
        return None
    parts = name.split(".")
    base = parts[-1]
    if base in _DESTRUCTIVE_FS_BASES:
        return name
    # os.remove / os.rename / shutil.move ... require a filesystem module receiver
    if base in ("remove", "rename", "move") and len(parts) >= 2:
        receiver = parts[-2].lower()
        if receiver in ("os", "shutil") or "path" in receiver:
            return name
    return None


# -----------------------------------------------------------------------------
# Public entry points
# -----------------------------------------------------------------------------


def scan_python(source: str) -> list[Finding]:
    """Scan a Python source string and return all findings.

    Returns an empty list for empty input or source that does not parse as
    Python (the caller is expected to gate on ``language_id == "python"``).
    """
    if not isinstance(source, str) or not source.strip():
        return []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError):
        return []

    lines = source.splitlines()

    # Build a child -> parent map once; the interlock checks walk ancestors.
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    visitor = _ScanVisitor(source, lines, parents)
    visitor.visit(tree)

    # Deterministic ordering: by line, then rule ID.
    return sorted(visitor.findings, key=lambda finding: (finding.line, finding.rule_id))


def scan_file(path: Union[str, Path]) -> list[Finding]:
    """Scan a Python file on disk and return all findings."""
    return scan_python(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "Finding",
    "scan_python",
    "scan_file",
    "R_SECRET_API_KEY",
    "R_SECRET_JWT",
    "R_SECRET_PASSWORD",
    "R_SECRET_CONNECTION_STRING",
    "R_DANGEROUS_EVAL",
    "R_DANGEROUS_EXEC",
    "R_UNSAFE_SQL",
    "R_MISSING_SAFETY_INTERLOC",
]