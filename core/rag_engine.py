import os
import logging
from typing import List, Dict, Any, Optional
from langchain_openai import OpenAIEmbeddings
from core.database import SessionLocal
from core.models import DocumentChunk
import uuid

logger = logging.getLogger(__name__)

class RAGEngine:
    """PostgreSQL pgvector-based RAG Engine (Replacing FAISS)."""

    def __init__(self):
        try:
            from app.core.config import settings
            key = settings.OPENAI_API_KEY
        except ImportError:
            key = os.getenv("OPENAI_API_KEY")
        
        try:
            self.embeddings = OpenAIEmbeddings(api_key=key)
        except Exception:
            self.embeddings = None
            logger.warning("OPENAI_API_KEY not found. RAG embeddings will fail.")

    def add_documents(self, documents: List[Dict[str, Any]]):
        """Add guidelines/documents to the vector store."""
        if not self.embeddings:
            return
            
        texts = [doc.get("text", "") for doc in documents]
        try:
            doc_embeddings = self.embeddings.embed_documents(texts)
            db = SessionLocal()
            try:
                for idx, doc in enumerate(documents):
                    chunk = DocumentChunk(
                        content=doc.get("text", ""),
                        embedding=doc_embeddings[idx]
                    )
                    db.add(chunk)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to add documents to Postgres RAG: {e}")
                db.rollback()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error embedding documents: {e}")

    def search(self, query: str, top_k: int = 3, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for relevant guidelines using pgvector cosine_distance."""
        if not self.embeddings:
            return []
            
        try:
            query_embedding = self.embeddings.embed_query(query)
            db = SessionLocal()
            try:
                docs = db.query(DocumentChunk).order_by(
                    DocumentChunk.embedding.cosine_distance(query_embedding)
                ).limit(top_k).all()
                
                results = []
                for doc in docs:
                    results.append({
                        "text": doc.content,
                        "relevance_score": 0.0,
                        "chunk_id": str(doc.id)
                    })
                return results
            except Exception as e:
                logger.error(f"RAG Postgres Search failed: {e}")
                return []
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error searching embeddings: {e}")
            return []

# Global instance
_rag_instance: Optional[RAGEngine] = None

def get_rag_engine() -> RAGEngine:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGEngine()
    return _rag_instance
