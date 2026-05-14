from __future__ import annotations

import os
import logging
import uuid
from typing import List, Dict, Any, Optional
from langchain_openai import OpenAIEmbeddings
from core.database import SessionLocal
from core.models import DocumentChunk
from sqlalchemy import text

logger = logging.getLogger(__name__)

class RAGEngine:
    """PostgreSQL pgvector-based RAG Engine (Replacing FAISS)."""

    def __init__(self):
        key = os.getenv("OPENAI_API_KEY")
        try:
            self.embeddings = OpenAIEmbeddings(api_key=key) if key else None
            if not key:
                logger.warning("OPENAI_API_KEY not found. RAG embeddings disabled.")
        except Exception:
            self.embeddings = None
            logger.warning("RAG embedding client failed to initialize.")

    def add_documents(self, documents: List[Dict[str, Any]], tenant_id: Optional[uuid.UUID] = None):
        """Add guidelines/documents to the vector store."""
        if not self.embeddings:
            return
            
        texts = [doc.get("text", "") for doc in documents]
        try:
            doc_embeddings = self.embeddings.embed_documents(texts)
            with SessionLocal() as db:
                for idx, doc in enumerate(documents):
                    chunk = DocumentChunk(
                        tenant_id=tenant_id,
                        content=doc.get("text", ""),
                        embedding=doc_embeddings[idx]
                    )
                    db.add(chunk)
                db.commit()
        except Exception as e:
            logger.error(f"Error adding documents to Postgres RAG: {e}")

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Search for relevant guidelines using pgvector cosine_distance."""
        if not self.embeddings:
            return []
            
        try:
            query_embedding = self.embeddings.embed_query(query)
            with SessionLocal() as db:
                dist = DocumentChunk.embedding.cosine_distance(query_embedding).label("dist")
                query_stmt = db.query(DocumentChunk, dist)
                if tenant_id is not None:
                    query_stmt = query_stmt.filter(DocumentChunk.tenant_id == tenant_id)
                rows = query_stmt.order_by(dist).limit(top_k).all()

                return [
                    {
                        "text": r.DocumentChunk.content,
                        "relevance_score": round(max(0.0, min(1.0, 1 - float(r.dist or 0.0))), 4),
                        "chunk_id": str(r.DocumentChunk.id),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"RAG Postgres Search failed: {e}")
            return []


class StubRAGEngine:
    """Safe fallback when pgvector or embeddings are unavailable."""

    def add_documents(self, documents: List[Dict[str, Any]], tenant_id: Optional[uuid.UUID] = None):
        logger.warning("RAG disabled; skipping %s document(s).", len(documents))

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        return []


def _pgvector_extension_available() -> bool:
    try:
        with SessionLocal() as db:
            result = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return result.scalar() == 1
    except Exception as e:
        logger.exception("RAG pgvector startup check failed; disabling RAG: %s", e)
        return False

# Global instance
_rag_instance: Optional[RAGEngine | StubRAGEngine] = None

def get_rag_engine() -> RAGEngine | StubRAGEngine:
    global _rag_instance
    if _rag_instance is None:
        if not _pgvector_extension_available():
            logger.error("pgvector extension not found — run: CREATE EXTENSION vector;")
            _rag_instance = StubRAGEngine()
        else:
            _rag_instance = RAGEngine()
    return _rag_instance
