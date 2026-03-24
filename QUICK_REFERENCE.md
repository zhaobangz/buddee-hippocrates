# Buddi Clinical Agent - Quick Reference

## 🚀 Get Started Fast

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
nano .env  # Add LLM_API_KEY

# 3. Launch Development Mode (starts Backend + Frontend)
chmod +x run-web-dev.sh
./run-web-dev.sh
```

**Go to:** http://localhost:5000

---

## 🏥 Clinical Agent Components

| Feature | Description | File |
|---------|-------------|------|
| **EHR Reader** | Clinical PDF/text ingestion | `tools/ehr_reader.py` |
| **Prior Auth** | Insurance-specific PA forms | `tools/prior_auth.py` |
| **Guidelines** | Look up ADA, ACC/AHA, etc. | `tools/clinical_guidelines.py` |
| **Safety** | Clinical action verification | `core/safety.py` |
| **Tracing** | Clinical activity oversight | `core/tracing.py` |

---

## 📁 Key Project Files

| File/Folder | Purpose |
|-------------|---------|
| `backend/api.py` | FastAPI Clinical Agent API |
| `web/` | Dashboard (HTML/CSS/JS) |
| `core/agent.py` | Clinical AI Orchestration |
| `run-web-dev.sh` | Dev launcher with logging |
| `requirements.txt` | Complete project libraries |

---

## 🔌 Core API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat` | POST | Interact with clinical agent |
| `/api/patient-context` | POST/GET | Set/get patient context |
| `/api/status` | GET | Clinical tool/safety status |
| `/api/audit-log` | GET | Safety validation history |
| `/docs` | GET | Interactive API documentation |

---

## 🛡 Clinical Safety Checks

- **Diagnosis Blocked**: Direct diagnosis attempts are rejected.
- **Prescription Blocked**: Medication orders are not permitted.
- **Human Approval Required**: Prior Authorization submission requires confirmation.
- **Audit Logging**: All clinical actions are logged to `audit_log.json`.

---

## 🔧 Deployment Quick Check

- **Local Development**: Use `run-web-dev.sh`.
- **Production-ready**: Architecture is ready for Cloud Run (GCP), App Service (Azure), or AppRunner (AWS).
- **Environment**: Always keep your LLM API keys in `.env`, never in source code.

---

**Status**: ✅ Clinical Agent Ready | ✅ Healthcare Tools Integrated | ✅ Cloud-Ready Architecture

**Time to first clinical brief**: < 2 minutes
**Dashboard status**: Connected (Green)
