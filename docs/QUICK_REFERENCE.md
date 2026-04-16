# Buddi Clinical Agent - Quick Reference

## 🚀 Emergency Startup (Absolute Path Mode)

```bash
# 1. Activate isolated environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Add LLM Credentials
cp .env.example .env && nano .env

# 3. Launch Premium Workspace (Starts Backend + Frontend)
python start.py
```

**Clinical Dashboard:** [http://localhost:5173](http://localhost:5173)
**Interactive API Docs:** [http://localhost:8001/docs](http://localhost:8001/docs)

---

## 🏥 Clinical UI Terminal Mapping

| Workflow Icon | Action | Backend Component |
| :--- | :--- | :--- |
| **👤 Demo** | Set Demo Patient Context | `/api/patient` (POST) |
| **⚠️ Risk** | Perform Risk Assessment | `/api/risk` (GET) |
| **🕰️ History** | Show Clinical History | `/api/patient` (GET) |
| **📋 PA** | Generate Prior Auth | `tools/clinical_workflows.py` |
| **🏥 Brief** | Load Patient Brief | `tools/ehr_reader.py` |
| **🚀 Shadow** | Agent QA Validation | `/api/shadow-mode/compare` |

---

## 🧠 Core Intelligence Circuits

| Feature | Intelligence Mode | Primary File |
| :--- | :--- | :--- |
| **Guideline RAG** | FAISS Vector Search + SentenceTransformers | `core/rag_engine.py` |
| **Agent Core** | Intent Router & Tool Orchestrator | `core/agent.py` |
| **Memory** | Encrypted Patient & Provider Context | `core/memory.py` |
| **Safety** | HIPAA-foundation Audit & Action Validator | `core/safety.py` |

---

## 🔌 API Quick-Map (Port 8001)

| Endpoint | Method | Result Layout |
| :--- | :--- | :--- |
| `/api/chat` | POST | Unified Clinical Response |
| `/api/risk` | GET | **Risk Heatmap Data** |
| `/api/patient` | GET | **Intelligence Brief + History** |
| `/api/shadow-mode/compare` | POST | **Side-by-Side Validation** |
| `/api/status` | GET | Terminal Heartbeat |
| `/api/audit` | GET | Global Activity Log |

---

## 🛡 Mandatory Safety Boundaries

- **Block (Red)**: Direct Diagnosis or Prescription creation is strictly prohibited.
- **Gated (Yellow)**: Prior Authorization submission and Referral scheduling require **Human Confirmation**.
- **Audit (Blue)**: All medical actions are serialized to `audit_log.json` for HIPAA foundations.

---

**Clinical Pulse**: 💚 **Connected** | **RAG Index**: 📚 **Grounding Active** | **UI/UX**: 💎 **Premium Dashboard Ready**

