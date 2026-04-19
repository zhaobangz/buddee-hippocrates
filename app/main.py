from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import chat, patient, risk, workflow, audit
from app.core.config import settings
from app.core.logging import logger

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Buddi — Production-ready backend for healthcare workflows."
)

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In prod, restrict to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(chat.router, prefix="/api/chat", tags=["Clinical Chat"])
app.include_router(patient.router, prefix="/api/patient", tags=["Patient Intelligence"])
app.include_router(risk.router, prefix="/api/risk", tags=["Risk Dashboard"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["Workflow Automation"])
app.include_router(audit.router, prefix="/api/audit", tags=["Safety & Compliance"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "buddi-clinical-backend"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
