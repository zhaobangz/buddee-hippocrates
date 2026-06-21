"""PostgreSQL pgvector-backed RAG engine.

Manual §2.2 week 2 strips LangChain from the prompt path. Embeddings are
now requested via the OpenAI SDK directly (``openai.embeddings.create``)
which:

  * Eliminates LangChain's quarterly abstraction churn (BUILD_PLAN.md §1).
  * Removes the indirection between Buddi and the actual HTTP call we
    audit and rate-limit.
  * Keeps the model pluggable via ``OPENAI_EMBED_MODEL`` (default
    ``text-embedding-3-large``) — matches the manual's
    "OpenAI embeddings only" guardrail.

The embedding path is the only place we send anything to OpenAI today;
the prompt path runs on Anthropic per ``core/llm_manager.py``. Because
the only thing we embed here is CMS guideline text (not PHI), this call
does *not* require the BAA tripwire. Per-tenant clinical-note embedding
will require additional safety review before it's enabled at scale.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from sqlalchemy import text

from core.database import SessionLocal
from core.models import DocumentChunk

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single retrieved guideline chunk (provider-agnostic)."""

    chunk_id: str
    text: str
    relevance_score: float


@runtime_checkable
class Retriever(Protocol):
    """Pluggable vector-retrieval interface (build-out B4.3).

    Lets the backend swap the pgvector implementation for Turbopuffer (or any
    other vector store) in a ~1-week project without touching call sites: a new
    backend just implements ``retrieve`` over a precomputed query embedding.
    Embedding generation stays OpenAI-only in ``RAGEngine`` (A1.3 guard).
    """

    async def retrieve(
        self,
        query_embedding: List[float],
        top_k: int,
        tenant_id: Optional[uuid.UUID],
    ) -> List[RetrievedChunk]:
        ...


DEFAULT_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
DEFAULT_EMBED_DIMENSIONS = 1536  # Must match Vector(1536) in core/models.py.


def _resolve_embed_model() -> str:
    return os.getenv("OPENAI_EMBED_MODEL", DEFAULT_EMBED_MODEL)


def _resolve_openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


class _EmbeddingsOnlyOpenAI:
    """Guard proxy exposing *only* the embeddings surface of the OpenAI SDK.

    Build-out A1.3 / manual §2.2 guardrail: OpenAI is embeddings-only in
    Buddi. Clinical-reasoning (chat/completions/responses) must route through
    Anthropic via ``core/llm_manager.py``. If any code accidentally tries to
    route a non-embedding call through OpenAI from the RAG path, fail loudly
    rather than silently sending a clinical prompt to the wrong vendor (which
    would also escape the BAA tripwire enforced on the Anthropic path).
    """

    def __init__(self, client: Any):
        # Stored in __dict__ so it does not trip __getattr__ below.
        self._client = client

    def __getattr__(self, name: str) -> Any:
        if name == "embeddings":
            return self._client.embeddings
        raise RuntimeError(
            f"OpenAI is embeddings-only in Buddi (attempted non-embedding "
            f"attribute '{name}'). Clinical-reasoning calls must route through "
            f"Anthropic via core/llm_manager.py. See build-out A1.3."
        )


class OpenAIEmbeddingClient:
    """Thin wrapper around the OpenAI SDK for embeddings only.

    Constructed lazily so module import doesn't require the API key to
    be set (tests, doc builds, etc.). All errors are surfaced to the
    caller — the RAGEngine wraps them in graceful fallbacks.
    """

    def __init__(self, api_key: str, model: str):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover — openai is pinned
            raise RuntimeError("openai SDK is required for RAG embeddings") from e
        # Wrap in the embeddings-only guard so a stray chat/completion call
        # routed through this client raises RuntimeError (build-out A1.3).
        self._client = _EmbeddingsOnlyOpenAI(OpenAI(api_key=api_key))
        self._model = model

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=list(texts))
        return [item.embedding for item in response.data]

    def embed_query(self, query: str) -> List[float]:
        response = self._client.embeddings.create(model=self._model, input=query)
        return list(response.data[0].embedding)


class RAGEngine:
    """PostgreSQL pgvector-based RAG engine (LangChain-free)."""

    def __init__(self):
        key = _resolve_openai_key()
        self._embed_model = _resolve_embed_model()
        if not key:
            logger.warning("OPENAI_API_KEY not found. RAG embeddings disabled.")
            self._client: Optional[OpenAIEmbeddingClient] = None
            return
        try:
            self._client = OpenAIEmbeddingClient(api_key=key, model=self._embed_model)
        except Exception as e:
            logger.warning("OpenAI embedding client failed to initialize: %s", e)
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        tenant_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Embed and persist documents. Returns the number of chunks written."""

        if not self._client:
            return 0
        contents = [doc.get("text", "") for doc in documents if doc.get("text")]
        if not contents:
            return 0
        try:
            embeddings = self._client.embed_documents(contents)
        except Exception as e:
            logger.error("RAG embedding call failed: %s", e)
            return 0

        written = 0
        with SessionLocal() as db:
            try:
                for content, embedding in zip(contents, embeddings):
                    db.add(
                        DocumentChunk(
                            tenant_id=tenant_id,
                            content=content,
                            embedding=embedding,
                        )
                    )
                    written += 1
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("RAG persistence failed: %s", e)
                return 0
        return written

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Cosine-distance retrieval over ``document_chunks``.

        Tenant-scoped at the application layer; the migration also adds an
        RLS policy so the DB rejects cross-tenant reads even if the filter
        is omitted.
        """

        if not self._client:
            return []

        try:
            query_embedding = self._client.embed_query(query)
        except Exception as e:
            logger.error("RAG query embedding failed: %s", e)
            return []

        try:
            with SessionLocal() as db:
                dist = DocumentChunk.embedding.cosine_distance(query_embedding).label("dist")
                stmt = db.query(DocumentChunk, dist)
                if tenant_id is not None:
                    stmt = stmt.filter(DocumentChunk.tenant_id == tenant_id)
                rows = stmt.order_by(dist).limit(top_k).all()
                return [
                    {
                        "text": r.DocumentChunk.content,
                        "relevance_score": round(
                            max(0.0, min(1.0, 1 - float(r.dist or 0.0))), 4
                        ),
                        "chunk_id": str(r.DocumentChunk.id),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("RAG Postgres search failed: %s", e)
            return []

    async def retrieve(
        self,
        query_embedding: List[float],
        top_k: int = 3,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> List[RetrievedChunk]:
        """``Retriever`` protocol impl: cosine search over a precomputed embedding.

        Unlike :meth:`search`, this takes an already-computed embedding so the
        embedding provider (OpenAI) and the vector store are cleanly separable
        — the swap point for Turbopuffer.
        """

        if not self._client:
            return []
        try:
            with SessionLocal() as db:
                dist = DocumentChunk.embedding.cosine_distance(query_embedding).label("dist")
                stmt = db.query(DocumentChunk, dist)
                if tenant_id is not None:
                    stmt = stmt.filter(DocumentChunk.tenant_id == tenant_id)
                rows = stmt.order_by(dist).limit(top_k).all()
                return [
                    RetrievedChunk(
                        chunk_id=str(r.DocumentChunk.id),
                        text=r.DocumentChunk.content,
                        relevance_score=round(max(0.0, min(1.0, 1 - float(r.dist or 0.0))), 4),
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.error("RAG retrieve failed: %s", e)
            return []


class StubRAGEngine:
    """Safe fallback when pgvector or embeddings are unavailable."""

    @property
    def enabled(self) -> bool:
        return False

    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        tenant_id: Optional[uuid.UUID] = None,
    ) -> int:
        logger.warning("RAG disabled; skipping %s document(s).", len(documents))
        return 0

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        return []

    async def retrieve(
        self,
        query_embedding: List[float],
        top_k: int = 3,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> List[RetrievedChunk]:
        return []


def _pgvector_extension_available() -> bool:
    try:
        with SessionLocal() as db:
            result = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return result.scalar() == 1
    except Exception as e:
        logger.exception("RAG pgvector startup check failed; disabling RAG: %s", e)
        return False


_rag_instance: Optional[RAGEngine | StubRAGEngine] = None


def get_rag_engine() -> RAGEngine | StubRAGEngine:
    """Return the singleton RAG engine, building it on first use."""

    global _rag_instance
    if _rag_instance is None:
        if not _pgvector_extension_available():
            logger.error("pgvector extension not found — run: CREATE EXTENSION vector;")
            _rag_instance = StubRAGEngine()
        else:
            _rag_instance = RAGEngine()
    return _rag_instance


def reset_rag_cache() -> None:
    """Drop the cached engine (used by tests that rotate the API key)."""

    global _rag_instance
    _rag_instance = None


__all__ = [
    "OpenAIEmbeddingClient",
    "RAGEngine",
    "StubRAGEngine",
    "get_rag_engine",
    "reset_rag_cache",
]
