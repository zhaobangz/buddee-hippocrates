import faiss
import numpy as np
import os
import pickle
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from core.config import Config
from core.safety import redact_pii

class RAGEngine:
    """FAISS-based Retrieval-Augmented Generation Engine for Clinical Guidelines."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.dimension = 384  # Dimension for all-MiniLM-L6-v2
        self.index = faiss.IndexFlatL2(self.dimension)
        self.metadata: List[Dict[str, Any]] = []
        self.index_path = os.path.join(os.path.dirname(Config.AUDIT_LOG_FILE), "guidelines_index.faiss")
        self.metadata_path = os.path.join(os.path.dirname(Config.AUDIT_LOG_FILE), "guidelines_metadata.pkl")
        
        # Load existing index if it exists
        self._load()

    def add_documents(self, documents: List[Dict[str, Any]]):
        """Add guidelines/documents to the vector store.
        
        Expected doc format: {"text": "...", "condition": "...", "source": "..."}
        """
        texts = [doc["text"] for doc in documents]
        embeddings = self.model.encode(texts)
        
        # Add to FAISS index
        self.index.add(np.array(embeddings).astype("float32"))
        
        # Store metadata
        self.metadata.extend(documents)
        self._save()

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for relevant guidelines based on a query."""
        query_embedding = self.model.encode([query])
        distances, indices = self.index.search(np.array(query_embedding).astype("float32"), top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.metadata):
                res = self.metadata[idx].copy()
                res["relevance_score"] = float(1 / (1 + distances[0][i]))
                results.append(res)
        
        return results

    def _save(self):
        """Save index and metadata to disk."""
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)

    def _load(self):
        """Load index and metadata from disk."""
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, "rb") as f:
                    self.metadata = pickle.load(f)
            except Exception as e:
                print(f"Error loading RAG index: {e}")

# Global instance
_rag_instance: Optional[RAGEngine] = None

def get_rag_engine() -> RAGEngine:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGEngine()
    return _rag_instance
