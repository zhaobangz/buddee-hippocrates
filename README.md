# Buddi Clinical Agent System

> **Healthcare Workflow Intelligence powered by Agentic AI**

Buddi Clinical Agent is an AI-powered clinical workflow system that automates healthcare administrative tasks, provides clinical decision support, and orchestrates care activities. Built with a modular agent architecture, it's designed to start with prior authorization automation and expand into a full clinical operating system.

## 🏥 What It Does

| Workflow | Description |
|----------|-------------|
| **Prior Authorization** | Generates and tracks insurance prior auth forms (Medicare, Medicaid, Commercial) |
| **Patient Brief** | Creates pre-visit intelligence briefs with risk flags, missing labs, and suggested questions |
| **Clinical Guidelines** | Maps patient conditions to ADA, ACC/AHA, GINA, APA guidelines with treatment step-up logic |
| **Follow-Up Tracking** | Automates patient follow-ups with symptom checks, medication adherence, and escalation |
| **Scheduling** | Coordinates labs, imaging, and referrals as a workflow orchestrator |
| **Safety Layer** | Validates actions, blocks diagnosis/prescription territory, and writes HIPAA audit logs |

## 🏗 Architecture

```
┌────────────────────────────────────────────────┐
│              Web UI / API Layer                │
│         (FastAPI + HTML/JS Frontend)           │
├────────────────────────────────────────────────┤
│              Agent Orchestrator                │
│     (Intent Detection → Workflow Routing)      │
├────────────────────────────────────────────────┤
│             Safety & Audit Layer               │
│   (Action validation, human approval, logs)    │
├────────────────────────────────────────────────┤
│            Medical Tool Layer                  │
│  ┌──────────┬──────────┬──────────────────┐   │
│  │EHR Reader│Prior Auth│Clinical Guidelines│   │
│  ├──────────┼──────────┼──────────────────┤   │
│  │Follow-Up │Scheduling│   (Extensible)   │   │
│  └──────────┴──────────┴──────────────────┘   │
├────────────────────────────────────────────────┤
│         Memory (Patient + Provider Context)    │
├────────────────────────────────────────────────┤
│              LLM Manager (DeepSeek)            │
└────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your LLM API key
```

### 3. Run the CLI

```bash
python main.py
```

### 4. Run the Web UI

```bash
# Start the backend API
python -m uvicorn backend.api:app --reload --port 8000

# Open web/index.html in your browser
```

## 📋 Usage Examples

```
> Set patient John Smith, ID 12345, diabetes, on metformin
✅ Patient context set

> Generate a prior authorization for insulin therapy
⚠ HUMAN APPROVAL REQUIRED (Prior Auth Submit)
> yes
📋 Prior Authorization Form generated (PA-XXXXXXXX)

> Look up clinical guidelines for diabetes
📚 ADA Standards of Care — treatment step-up suggestions

> Create a medication adherence follow-up
✅ Follow-up created (FU-XXXXXXXX)

> Schedule a lab for HbA1c
🔬 Lab scheduled (TASK-XXXXXXXX)
```

## 🛡 Safety & Compliance

- **No diagnoses or prescriptions** — the system blocks these action types
- **Human approval gates** — sensitive actions require explicit confirmation
- **Audit logging** — all actions logged to `audit_log.json` (HIPAA foundation)
- **Response sanitization** — LLM outputs scanned for unsafe clinical language

## 🗺 Product Roadmap

| Phase | Timeline | Scope |
|-------|----------|-------|
| 🟢 Phase 1 | 0–2 months | Prior Auth MVP + Patient Brief |
| 🟡 Phase 2 | 2–4 months | Follow-up tracking + notifications |
| 🔵 Phase 3 | 4–8 months | Full workflow automation |
| 🔴 Phase 4 | 8+ months | AI operating system for clinics |

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

## ⚖️ Regulatory Notes

- **HIPAA**: Audit logging foundation in place. Production deployment requires encryption, access control, and BAA agreements.
- **FDA**: System avoids diagnosis/prescription territory to minimize regulatory risk.
- **EHR Integration**: Starts with PDF/text uploads. Future integration with Epic/Cerner via FHIR APIs.
