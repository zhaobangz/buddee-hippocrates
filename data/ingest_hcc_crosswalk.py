import csv
import io
import logging
from dataclasses import dataclass
from typing import List

from core.rag_engine import get_rag_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class HCCRecord:
    icd10: str
    hcc_code: str
    weight: float
    desc: str
    category: str

def parse_cms_csv_mock() -> List[HCCRecord]:
    """
    Mock parser for CMS HCC crosswalks.
    In a real scenario, this would parse a downloaded CMS CSV.
    """
    csv_data = """icd10,hcc_code,weight,desc,category
E11.40,HCC18,0.318,Type 2 diabetes mellitus with diabetic neuropathy,Diabetes
I50.9,HCC85,0.323,Heart failure, unspecified,Congestive Heart Failure
J44.9,HCC111,0.326,Chronic obstructive pulmonary disease, unspecified,COPD
F32.9,HCC59,0.395,Major depressive disorder, single episode, unspecified,Psychiatric
N18.3,HCC138,0.224,Chronic kidney disease, stage 3 (unspecified),CKD"""

    records = []
    reader = csv.DictReader(io.StringIO(csv_data))
    for row in reader:
        records.append(HCCRecord(
            icd10=row["icd10"],
            hcc_code=row["hcc_code"],
            weight=float(row["weight"]),
            desc=row["desc"],
            category=row["category"]
        ))
    return records

def ingest_cms_hcc_models():
    """
    Ingests CMS ICD-10 to HCC crosswalk models into the vector database.
    """
    logger.info("Starting HCC Model Ingestion...")
    rag = get_rag_engine()
    
    records = parse_cms_csv_mock()
    documents_to_add = []
    
    for record in records:
        text = f"ICD-10: {record.icd10} maps to HCC: {record.hcc_code}. Risk Weight: {record.weight}. Description: {record.desc}"
        doc = {
            "text": text,
            "condition": record.category,
            "source": "CMS_2024_V28",
            "type": "HCC_CROSSWALK",
            "year": "2024"
        }
        documents_to_add.append(doc)
        
    logger.info(f"Adding {len(documents_to_add)} records to the pgvector store.")
    rag.add_documents(documents_to_add)
    logger.info("Ingestion complete.")

if __name__ == "__main__":
    ingest_cms_hcc_models()
