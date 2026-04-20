import os
import logging
from typing import List, Dict, Any
from langchain_openai import OpenAIEmbeddings
from app.core.config import settings
from core.database import SessionLocal
from core.models import DocumentChunk

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self):
        try:
            self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        except Exception:
            self.embeddings = None
            logger.warning("OPENAI_API_KEY not found. RAG embeddings will fail.")

    def retrieve(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        if not self.embeddings:
            return []
            
        try:
            query_embedding = self.embeddings.embed_query(query)
            db = SessionLocal()
            try:
                # pgvector natively supports cosine search if enabled
                docs = db.query(DocumentChunk).order_by(
                    DocumentChunk.embedding.cosine_distance(query_embedding)
                ).limit(k).all()
                
                results = []
                for doc in docs:
                    results.append({
                        "content": doc.content,
                        "score": 0.0, 
                        "chunk_id": str(doc.id)
                    })
                return results
            except Exception as e:
                logger.error(f"RAG Retrieval failed (likely due to missing Postgres DB or pgvector extension): {e}")
                return []
            finally:
                db.close()
        except Exception as e:
             logger.error(f"Embedding failure: {e}")
             return []

rag_engine = RAGService()
