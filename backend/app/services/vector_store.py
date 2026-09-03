"""ChromaDB-backed vector store for trusted ReviewX grounding context.

This service stores the authoritative "why / how to fix" guidance for every
ReviewX AST rule in a local persistent ChromaDB collection and retrieves the
most relevant snippets at explain-time.

Design notes
------------
* Heavy dependencies (``chromadb``, ``sentence_transformers``) are imported
  lazily inside functions so this module can always be imported -- even when
  those packages are not installed -- and so the embedding model is only
  downloaded/loaded on first use.
* The embedding model is ``sentence-transformers/all-MiniLM-L6-v2`` (384-d).
* If ChromaDB is unavailable, the collection is empty, or retrieval fails for
  any reason, ``get_grounding_context`` degrades gracefully to the built-in
  static guidance text instead of raising.
* API keys / secrets are never stored; only rule guidance text.

Environment variables
---------------------
REVIEWX_CHROMA_DIR       Overrides the persistent ChromaDB directory.
REVIEWX_EMBEDDING_MODEL  Overrides the sentence-transformers model id.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

# Rule IDs are pulled from the (already verified) AST scanner so that the
# grounding data always stays in sync with the rules the scanner emits.
from app.services.ast_parser import (
    R_DANGEROUS_EVAL,
    R_DANGEROUS_EXEC,
    R_MISSING_SAFETY_INTERLOC,
    R_SECRET_API_KEY,
    R_SECRET_CONNECTION_STRING,
    R_SECRET_JWT,
    R_SECRET_PASSWORD,
    R_UNSAFE_SQL,
)

logger = logging.getLogger(__name__)

# Opt out of ChromaDB's anonymous telemetry before the library is imported.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

COLLECTION_NAME = "reviewx_rules"
EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_TOP_K = 3

# Persistent store location. Default: <backend>/data/chroma
_DEFAULT_CHROMA_DIR = Path(__file__).resolve().parents[2] / "data" / "chroma"


def default_chroma_dir() -> str:
    """Return the ChromaDB persistence directory (env override supported)."""
    return os.environ.get("REVIEWX_CHROMA_DIR", str(_DEFAULT_CHROMA_DIR))


# Module-level caches. Guarded by _init_lock so concurrent calls initialize
# each resource exactly once.
_init_lock = threading.Lock()
_client = None
_collection = None
_embedder = None
_ready: Optional[bool] = None  # None == not yet probed


def _embedding_model_id() -> str:
    """Return the configured sentence-transformers model identifier."""
    return os.environ.get("REVIEWX_EMBEDDING_MODEL", EMBEDDING_MODEL_ID)
# -----------------------------------------------------------------------------
# Lazy resource initialisation (sentence-transformers + ChromaDB)
# -----------------------------------------------------------------------------


def _get_embedder() -> Any:
    """Lazily load and cache the SentenceTransformer embedding model."""
    global _embedder
    with _init_lock:
        if _embedder is None:
            # Imported here so the module imports fine without the package.
            from sentence_transformers import SentenceTransformer

            model_id = _embedding_model_id()
            logger.info("Loading embedding model '%s' (first call downloads it).", model_id)
            _embedder = SentenceTransformer(model_id)
    return _embedder


def _encode_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with the cached MiniLM model (384-d vectors)."""
    if not texts:
        return []
    model = _get_embedder()
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return [vector.tolist() for vector in vectors]


def _get_collection() -> Any:
    """Lazily create the persistent ChromaDB client and rule collection.

    ``embedding_function=None`` means ChromaDB will not download its default
    ONNX embedder -- we always pass our own embeddings explicitly.
    """
    global _client, _collection
    with _init_lock:
        if _collection is None:
            import chromadb

            chroma_dir = default_chroma_dir()
            logger.info("Opening persistent ChromaDB at '%s'.", chroma_dir)
            _client = chromadb.PersistentClient(path=chroma_dir)
            _collection = _client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
    return _collection


def is_available() -> bool:
    """Probe whether ChromaDB + the embedding model are usable right now."""
    try:
        _get_collection()
        _get_embedder()
        return True
    except Exception:  # pragma: no cover - depends on the local environment
        logger.debug("Vector store unavailable.", exc_info=True)
        return False
# -----------------------------------------------------------------------------
# Trusted grounding content for every ReviewX rule.
#
# Each entry carries a short ``summary`` (why the scanner flags this) and a
# ``remediation`` (how to fix it safely).  These strings are the authoritative
# knowledge base that gets embedded into ChromaDB and is also used as the
# graceful fallback when the vector store is unavailable.
# -----------------------------------------------------------------------------

_RULE_GUIDANCE: dict[str, dict[str, str]] = {
    R_SECRET_API_KEY: {
        "title": "Hardcoded API key",
        "summary": (
            "Hardcoded API keys (AWS AKIA..., OpenAI sk-..., GitHub ghp_..., "
            "Slack xox..., Stripe sk_live..., SendGrid SG...., Google AIza..., "
            "or PEM private keys) expose credentials to every developer, CI log, "
            "and leaked artifact that touches the repository. They are also "
            "impossible to rotate cleanly once committed."
        ),
        "remediation": (
            "Remove the literal, revoke/rotate the exposed credential, and load it "
            "at runtime from an environment variable or secret manager "
            "('os.environ.get(\"API_KEY\")'). Never commit key material, even in "
            "test fixtures."
        ),
    },
    R_SECRET_JWT: {
        "title": "Hardcoded JWT / bearer token",
        "summary": (
            "A JWT is a signed bearer credential; a literal token embedded in code "
            "(for example the 'eyJ...' header shape) grants anyone with file access "
            "the capabilities the token was issued for, and any past exposure means "
            "the token must be treated as compromised."
        ),
        "remediation": (
            "Do not embed JWTs. Issue tokens at runtime, keep signing secrets in a "
            "vault, and use short-lived tokens with rotation and revocation lists "
            "so a leaked token dies automatically."
        ),
    },
    R_SECRET_PASSWORD: {
        "title": "Hardcoded password",
        "summary": (
            "Plaintext passwords in source files are readable by any code reviewer, "
            "deployed container, package, or leaked backup. Hardcoded passwords are "
            "also frequently reused across systems, amplifying a single exposure."
        ),
        "remediation": (
            "Delete the literal and rotate the password. Inject it at runtime from "
            "env vars or a secrets manager, and prefer short-lived credentials "
            "(service accounts, scoped tokens) over shared passwords."
        ),
    },
    R_SECRET_CONNECTION_STRING: {
        "title": "Connection string with embedded credentials",
        "summary": (
            "Connection strings that embed 'user:password@host' (for example "
            "mysql://, postgres://, mongodb+srv://, or ODBC DSNs with Password=) "
            "leak database credentials and grant direct database access to anyone "
            "with the source code."
        ),
        "remediation": (
            "Move the DSN to an environment variable ('DATABASE_URL') or a secrets "
            "manager, use a least-privilege account, and rotate credentials "
            "immediately after any exposure."
        ),
    },
R_DANGEROUS_EVAL: {
        "title": "eval() dynamic code execution",
        "summary": (
            "eval() executes arbitrary Python expressions at runtime. When any "
            "part of its argument can be influenced by user input, an attacker "
            "gains full code-execution on the host -- the most severe class of "
            "vulnerability."
        ),
        "remediation": (
            "Avoid eval() entirely. For literal parsing use ast.literal_eval; for "
            "real logic prefer data-driven design (dicts of callables) or a strict "
            "domain-specific language. Never pass untrusted input to eval() with "
            "default builtins."
        ),
    },
    R_DANGEROUS_EXEC: {
        "title": "exec() dynamic code execution",
        "summary": (
            "exec() compiles and runs arbitrary code, including whole statements. "
            "With untrusted input it is equivalent to remote code execution and can "
            "read files, exfiltrate secrets, or destroy the host."
        ),
        "remediation": (
            "Never feed untrusted input to exec(). Refactor to declarative/allow-"
            "listed logic. If dynamic evaluation is truly required, isolate it in a "
            "locked-down subprocess with no network access and strict resource "
            "limits."
        ),
    },
    R_UNSAFE_SQL: {
        "title": "SQL built with string interpolation",
        "summary": (
            "Building SQL through '+' concatenation, f-strings, %-formatting, or "
            ".format() lets crafted input change the query structure. SQL injection "
            "can read, modify, or delete entire tables and bypass authentication."
        ),
        "remediation": (
            "Use parameterized queries / prepared statements with driver-native "
            "placeholders ('?', '%s', ':name'). Never concatenate or interpolate "
            "user input into the SQL text; treat identifiers needing dynamic names "
            "via an allow-list."
        ),
    },
    R_MISSING_SAFETY_INTERLOC: {
        "title": "Missing safety interlock",
        "summary": (
            "Destructive operations without a confirmation guard (for example "
            "os.remove / shutil.rmtree) and locks acquired without a matching "
            "release create footguns that cause data loss, deadlocks, or filesystem "
            "damage in production."
        ),
        "remediation": (
            "Guard destructive filesystem calls with an explicit confirmation path "
            "(CLI '--force'/'--yes', an interactive input() check, or a business-"
            "rule gate). Always pair lock.acquire() with release() -- preferably by "
            "using 'with lock:' so the interpreter guarantees the interlock."
        ),
    },
}


def guidance_for(rule_id: str) -> Optional[dict[str, str]]:
    """Return the static guidance dict for ``rule_id`` (or ``None``)."""
    return _RULE_GUIDANCE.get(rule_id)
# -----------------------------------------------------------------------------
# Seeding the collection
# -----------------------------------------------------------------------------


def _seed_documents() -> list[tuple[str, str, dict[str, str]]]:
    """Build ``(id, document, metadata)`` entries for the full rule library."""
    entries: list[tuple[str, str, dict[str, str]]] = []
    for rule_id, guidance in _RULE_GUIDANCE.items():
        entries.append(
            (
                f"{rule_id}:summary",
                f"[ReviewX {rule_id}] {guidance['title']}\n{guidance['summary']}",
                {"rule_id": rule_id, "kind": "summary"},
            )
        )
        entries.append(
            (
                f"{rule_id}:remediation",
                f"[ReviewX {rule_id}] Remediation\n{guidance['remediation']}",
                {"rule_id": rule_id, "kind": "remediation"},
            )
        )
    return entries


def seed_grounding_data(force: bool = False) -> int:
    """Embed and upsert the trusted grounding documents into ChromaDB.

    Args:
        force: re-upsert even when the collection is already populated.

    Returns:
        Number of documents now in the collection.

    Raises:
        RuntimeError: when ChromaDB or the embedding model cannot be used.
    """
    collection = _get_collection()
    if not force and collection.count() > 0:
        return collection.count()

    docs = _seed_documents()
    ids = [entry[0] for entry in docs]
    documents = [entry[1] for entry in docs]
    metadatas = [entry[2] for entry in docs]
    embeddings = _encode_texts(documents)

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    count = collection.count()
    logger.info(
        "Seeded %d grounding documents for %d rules.",
        count,
        len(_RULE_GUIDANCE),
    )
    return count


def count_grounding_documents() -> int:
    """Return how many documents the collection holds (0 if unavailable)."""
    try:
        return _get_collection().count()
    except Exception:  # pragma: no cover - environment dependent
        return 0


# -----------------------------------------------------------------------------
# Retrieval
# -----------------------------------------------------------------------------


def _fallback_context(rule_id: str) -> str:
    """Built-in static context used whenever the vector store is unavailable."""
    guidance = _RULE_GUIDANCE.get(rule_id)
    if not guidance:
        return ""
    return (
        f"[ReviewX {rule_id}] {guidance['title']}\n"
        f"Summary: {guidance['summary']}\n"
        f"Remediation: {guidance['remediation']}"
    )


def get_grounding_context(
    rule_id: str,
    snippet: str,
    top_k: int = DEFAULT_TOP_K,
) -> str:
    """Retrieve the most relevant trusted context for a rule finding.

    Always returns a string (possibly empty for unknown rule ids) and never
    raises: any ChromaDB / embedding-model failure downgrades to the built-in
    static guidance for ``rule_id``.
    """
    static_context = _fallback_context(rule_id)

    try:
        collection = _get_collection()

        # Auto-seed once when the collection is empty so first use works out
        # of the box; if seeding itself fails we simply fall back below.
        if collection.count() == 0:
            seed_grounding_data()

        if collection.count() == 0:
            return static_context

        query = f"{rule_id}: {snippet}" if snippet else rule_id
        vector = _encode_texts([query])[0]
        n_results = min(max(top_k, 1), collection.count())
        result = collection.query(
            query_embeddings=[vector],
            n_results=n_results,
            where={"rule_id": rule_id},
            include=["documents", "metadatas"],
        )
        documents = (result.get("documents") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
    except Exception as exc:  # noqa: BLE001 - graceful degradation is intended
        logger.warning(
            "Grounding retrieval failed; using static fallback: %r", exc
        )
        return static_context

    if not documents:
        return static_context

    rendered = [static_context]
    for index, doc in enumerate(documents):
        kind = "info"
        try:
            metadata = metadatas[index] if index < len(metadatas) else None
            kind = str(metadata.get("kind", "info")) if metadata else "info"
        except (IndexError, AttributeError, TypeError):
            kind = "info"
        rendered.append(f"\n--- Related {kind} ---\n{doc}")
    return "".join(rendered)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

__all__ = [
    "COLLECTION_NAME",
    "EMBEDDING_MODEL_ID",
    "default_chroma_dir",
    "is_available",
    "guidance_for",
    "seed_grounding_data",
    "count_grounding_documents",
    "get_grounding_context",
]
