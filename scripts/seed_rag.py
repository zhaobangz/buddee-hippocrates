"""
Seed script for Buddi Clinical RAG Engine
Adds clinical guidelines to the vector store.
"""
from core.rag_engine import get_rag_engine

def seed():
    print("🌱 Seeding Clinical RAG Engine...")
    rag = get_rag_engine()
    
    guidelines = [
        {
            "text": "ADA 2026: For patients with Type 2 Diabetes and high A1C (>7.0%), consider intensifying medication with SGLT2 inhibitors or GLP-1 receptor agonists if cardiovascular or renal benefits are desired.",
            "condition": "Diabetes",
            "source": "ADA Standards of Care 2026"
        },
        {
            "text": "ACC/AHA Hypertension Guidelines: Normal BP is <120/80. Stage 1 Hypertension is 130-139 / 80-89. Stage 2 is >=140 / >=90. Treat Stage 2 with lifestyle + 2 medications from different classes.",
            "condition": "Hypertension",
            "source": "ACC/AHA 2025"
        },
        {
            "text": "Medication Interaction: Lisinopril and Metformin have no major contraindications, but renal function (Creatinine/eGFR) should be monitored closely in elderly patients.",
            "condition": "General",
            "source": "Clinical Pharmacy Guide"
        }
    ]
    
    rag.add_documents(guidelines)
    print("✅ RAG Seeding Complete. 3 guidelines added.")

if __name__ == "__main__":
    seed()
