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
chmod +x run-web.sh && ./run-web.sh
```

**Clinical Dashboard:** [http://localhost:3000](http://localhost:3000)
**Interactive API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🏥 Clinical UI Terminal Mapping

| Workflow Icon | Action | Backend Component |
| :--- | :--- | :--- |
| **👤 Demo** | Set Demo Patient Context | `/api/patient-context` |
| **⚠️ Risk** | Perform Risk Assessment | `/api/risk-assessment` |
| **🕰️ History** | Show Clinical History | `/api/patient-history` |
| **📋 PA** | Generate Prior Auth | `tools/prior_auth.py` |
| **🏥 Brief** | Load Patient Brief | `tools/ehr_reader.py` |
| **🎙️ Mic** | Start Audio Capture | `ui/widget.py` |

---

## 🧠 Core Intelligence Circuits

| Feature | Intelligence Mode | Primary File |
| :--- | :--- | :--- |
| **Guideline RAG** | FAISS Vector Search + SentenceTransformers | `core/rag_engine.py` |
| **Agent Core** | Intent Router & Tool Orchestrator | `core/agent.py` |
| **Memory** | Encrypted Patient & Provider Context | `core/memory.py` |
| **Safety** | HIPAA-foundation Audit & Action Validator | `core/safety.py` |

---

## 🔌 API Quick-Mapp (Port 8000)

| Endpoint | Method | Result Layout |
| :--- | :--- | :--- |
| `/api/chat` | POST | Unified Clinical Response |
| `/api/risk-assessment` | GET | **Risk Heatmap Data** |
| `/api/shadow-mode/compare` | POST | **Side-by-Side Validation** |
| `/api/status` | GET | Terminal Heartbeat |
| `/api/audit-log` | GET | Global Activity Log |

---

## 🛡 Mandatory Safety Boundaries

- **Block (Red)**: Direct Diagnosis or Prescription creation is strictly prohibited.
- **Gated (Yellow)**: Prior Authorization submission and Referral scheduling require **Human Confirmation**.
- **Audit (Blue)**: All medical actions are serialized to `audit_log.json` for HIPAA foundations.

---

**Clinical Pulse**: 💚 **Connected** | **RAG Index**: 📚 **Grounding Active** | **UI/UX**: 💎 **Premium Dashboard Ready**
