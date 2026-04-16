import os
from typing import List, Dict, Any
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from app.core.config import settings

class RAGService:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        self.vector_db = None
        self._initialize_db()

    def _initialize_db(self):
        # In a real app, this would load from a persistent path or cloud DB
        # For demo purposes, we'll create a mock index if it doesn't exist
        mock_data = [
            "ADA Guidelines: Type 2 Diabetes should be managed with Metformin as first-line therapy unless contraindicated.",
            "ACC/AHA Guidelines: Blood pressure target for hypertensive patients with CVD risk should be <130/80 mmHg.",
            "Prior Auth Rules: Knee MRI requires 6 weeks of conservative therapy (physical therapy) first."
        ]
        if os.path.exists("./guidelines_index.faiss"):
             self.vector_db = FAISS.load_local("./guidelines_index.faiss", self.embeddings, allow_dangerous_deserialization=True)
        else:
            self.vector_db = FAISS.from_texts(mock_data, self.embeddings)

    def retrieve(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        docs = self.vector_db.similarity_search_with_score(query, k=k)
        results = []
        for doc, score in docs:
            results.append({
                "content": doc.page_content,
                "score": float(score),
                "source": doc.metadata.get("source", "Clinical Guidelines")
            })
        return results

rag_engine = RAGService()
