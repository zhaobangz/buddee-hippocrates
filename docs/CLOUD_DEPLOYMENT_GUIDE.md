# Cloud Deployment Guide - Buddi Clinical Agent

Buddi Clinical Agent is architecture-ready for high-availability deployment to AWS, Google Cloud (GCP), or Azure. This guide details the process for migrating the clinical system from a local terminal to a production cloud environment.

## 🏗 Architecture Compliance

- ✅ **Backend**: Stateless FastAPI REST API (OIDC & JWT compatible).
- ✅ **Frontend**: Premium multi-view workspace (CDN & Static Hosting ready).
- ✅ **AI Layers**: RAG engine with FAISS vector store persistence.
- ✅ **HIPAA Foundation**: Integrated clinical audit logging (Serialized JSON).
- ✅ **Isolation**: Environment Guardian enabled for containerized stability.

## 📡 Deployment Matrix

| Provider | Backend Hosting | Frontend Hosting | Persistent Memory |
| :--- | :--- | :--- | :--- |
| **Google Cloud** | Cloud Run (Container) | Firebase Hosting | Cloud Storage / Filestore |
| **AWS** | AppRunner / ECS | S3 + CloudFront | EFS / RDS |
| **Azure** | App Service | Static Web Apps | Azure Files / Blob |

## 🚀 Deployment Checklist

1. **Verify Clinical RAG**: Check that your guidelines (ADA, ACC/AHA) are indexed in the `guidelines_index.faiss`.
2. **Setup Provider**: Choose your LLM engine (DeepSeek-V3, GPT-4o, etc.) and update the production `.env`.
3. **Internal URLs**: Update `web/script.js` to point to your secure production API domain instead of `localhost:8000`.
4. **CORS Protocol**: Update `backend/api.py` to allow only your production frontend origin.

## ☁️ Google Cloud Deployment (Recommended)

### 1. Containerize & Push
```bash
# Push to Google Artifact Registry
gcloud builds submit --tag gcr.io/YOUR-PROJECT/buddi-clinical-core
```

### 2. Launch Clinical Core (Cloud Run)
```bash
gcloud run deploy buddi-terminal-api \
  --image gcr.io/YOUR-PROJECT/buddi-clinical-core \
  --platform managed \
  --region us-central1 \
  --set-env-vars "LLM_PROVIDER=deepseek,ENABLE_SAFETY_LAYER=True" \
  --allow-unauthenticated
```

### 3. Static Hosting (Frontend)
Deploy the `web/` folder to Firebase Hosting or a GCS Bucket configured for static website hosting.

## 🛡 Production Security & HIPAA

- **🔐 TLS/SSL**: Mandatory HTTPS for all clinical data in transit.
- **📄 Immutable Audits**: Map a Persistent Volume (PV) to `/data/` to ensure `audit_log.json` and `memory.json` are preserved across redeployments.
- **🗳 RAG Persistence**: Ensure the `.faiss` vector index is included in the container build or loaded via cloud storage on startup.
- **🔑 Secrets**: Use Cloud Secret Manager for your LLM API keys and clinical credentials.
- **🐳 Environment Guardian**: The `./run-web.sh` logic is pre-configured to ensure the agent runs in a clean, isolated environment even within diverse cloud container runtimes.

---

**Status**: ✅ **Cloud-Ready**. The Buddi Clinical Agent is structured for elastic scaling and healthcare-grade reliability in the cloud.
