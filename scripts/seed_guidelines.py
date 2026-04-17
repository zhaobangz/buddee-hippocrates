from core.rag_engine import get_rag_engine

def seed_guidelines():
    rag = get_rag_engine()
    
    guidelines = [
        {
            "text": "HCC 18: Diabetes with Chronic Complications. Requires documentation of the specific complication (e.g., nephropathy, neuropathy) linked to the diabetes in the same encounter note for revenue integrity capture.",
            "condition": "Diabetes",
            "source": "CMS HCC 2024"
        },
        {
            "text": "NCCN Oncology Guideline (Lung-1): First-line therapy for metastatic NSCLC with high PD-L1 (>=50%) should include Pembrolizumab monotherapy unless contraindicated. Documentation must include PD-L1 test results.",
            "condition": "NSCLC",
            "source": "NCCN 2025"
        },
        {
            "text": "AGA Gastroenterology Guideline: Biologic therapy for moderate-to-severe Crohn's disease should be initiated after failure of conventional therapies (corticosteroids/immunomodulators). Verify 'Step Therapy' compliance before Prior Auth submission.",
            "condition": "Crohn's Disease",
            "source": "AGA 2024"
        },
        {
            "text": "HCC 111: Chronic Obstructive Pulmonary Disease (COPD). Documentation must include current treatment regimen and severity assessment (e.g., GOLD stage) for accurate Hierarchical Condition Category weighting.",
            "condition": "COPD",
            "source": "CMS HCC 2024"
        },
        {
            "text": "HCC 85: Congestive Heart Failure (CHF). Coding requires specification of the type (systolic, diastolic, or combined) and acuity (acute, chronic, or acute on chronic). Avoid 'heart failure' unspecified labels.",
            "condition": "CHF",
            "source": "CMS HCC 2024"
        }
    ]
    
    print(f"Seeding {len(guidelines)} clinical guidelines into FAISS index...")
    rag.add_documents(guidelines)
    print("Success: Guidelines indexed.")

if __name__ == "__main__":
    seed_guidelines()
