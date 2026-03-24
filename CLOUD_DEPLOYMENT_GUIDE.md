# Cloud Deployment Guide - Buddi Clinical Agent

Buddi Clinical Agent is architecture-ready for deployment to AWS, Google Cloud, or Azure. This guide provides instructions for preparing and deploying the clinical system to a production environment.

## Architecture Status

✅ **Backend**: Stateless FastAPI API (container-ready).
✅ **Frontend**: Static Web UI (CDN-ready).
✅ **Medical Data**: Audit logs and memory persist to JSON/Audit files.
✅ **HIPAA Foundation**: Integrated audit logging and safety boundary checks.

## Deployment Options

| Provider | Backend | Frontend | Monthly Cost |
|----------|---------|----------|--------------|
| **AWS** | EC2 or AppRunner | S3 + CloudFront | $10-30 |
| **Google Cloud** | Cloud Run (Recommended) | Firebase Hosting | Free - $10 |
| **Azure** | App Service | Static Web Apps | $10-20 |

## Preparation Checklist

1. **Verify Clinical Tools**: Ensure ` EHR Reader`, `Prior Auth`, and `Guidelines` tools are tested locally.
2. **Setup LLM Provider**: Update `.env` with your production `LLM_API_KEY`.
3. **CORS Configuration**: Update `backend/api.py` to only allow your staging/production domain.
4. **Environment Variables**: Configure all clinical agent settings via environment variables in your cloud provider's console.

## For Google Cloud (Cloud Run) - Recommended

### 1. Build & Push Container
```bash
gcloud builds submit --tag gcr.io/YOUR-PROJECT/buddi-clinical-agent
```

### 2. Deploy to Cloud Run
```bash
gcloud run deploy buddi-clinical-agent \
  --image gcr.io/YOUR-PROJECT/buddi-clinical-agent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### 3. Deploy Frontend (Firebase Hosting)
```bash
# In the /web directory
firebase init hosting
firebase deploy
```

## Critical Production Changes

### 1. Update Frontend API Link
File: `web/script.js`
```javascript
// Change from local to your cloud backend URL
const API_BASE_URL = 'https://your-clinical-api-endpoint.com/api';
```

### 2. Configure Clinical Safety Layer
Ensure your production environment variables include:
```
ENABLE_SAFETY_LAYER=True
ENABLE_AUDIT_LOG=True
REQUIRE_HUMAN_APPROVAL=True
AUDIT_LOG_FILE=/data/audit_log.json
```

### 3. Persistent Storage
For production, map a cloud-native storage volume (like Google Cloud Storage or AWS EFS) to the folder containing your `audit_log.json` and `memory.json`.

## Security & HIPAA Compliance Reminders

- ✅ **HTTPS**: Always use HTTPS for all clinical data transit.
- ✅ **Audit Logging**: Ensure `audit_log.json` is backed up and immutable.
- ✅ **Secrets**: Use Secret Manager (Cloud Secrets) for LLM API keys.
- ✅ **Encryption**: Enable volume-level encryption for clinical data at rest.
- ✅ **Access Control**: Restrict API access using standard authentication (e.g., JWT).

---

**Status**: ✅ Cloud-Ready Architecture | ✅ HIPAA Foundation | ✅ Deployment-Friendly
