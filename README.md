# Buddi Clinical Agent System

> **Healthcare Workflow Intelligence powered by Agentic AI**

Buddi Clinical Agent is an AI-powered clinical workflow system that automates healthcare administrative tasks, provides clinical decision support, and orchestrates care activities. Built with a modular agent architecture, it's designed to start with prior authorization automation and expand into a full clinical operating system.

## 🏥 Clinical Workflows

| Workflow | Description |
|----------|-------------|
| **Prior Authorization** | Generates and tracks insurance prior auth forms (Medicare, Medicaid, Commercial) |
| **Patient Brief** | Creates pre-visit intelligence briefs with risk flags, missing labs, and suggested questions |
| **Clinical Guidelines** | Maps patient conditions to ADA, ACC/AHA, GINA, APA guidelines with treatment step-up logic |
| **Follow-Up Tracking** | Automates patient follow-ups with symptom checks, medication adherence, and escalation |
| **Scheduling** | Coordinates labs, imaging, and referrals as a workflow orchestrator |
| **Safety Layer** | Validates clinical actions, blocks unauthorized territory, and writes HIPAA-ready audit logs |

## 🏗 Modular Architecture

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
│  │Follow-Up │Scheduling│   Web Search     │   │
│  └──────────┴──────────┴──────────────────┘   │
├────────────────────────────────────────────────┤
│         Memory (Patient + Provider Context)    │
├────────────────────────────────────────────────┤
│              LLM Manager (DeepSeek)            │
└────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Install Dependencies
Ensure you have Python 3.9+ installed, then run:
```bash
# Install core AI, web, and medical libraries
pip install -r requirements.txt

# macOS only: Install system dependencies for voice/summarization
brew install portaudio tesseract ffmpeg
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and add your LLM API key
```

### 3. Run the System
Use the development launcher to start both the Backend and Frontend:
```bash
chmod +x run-web-dev.sh
./run-web-dev.sh
```
The Web UI will be available at: **http://localhost:5000**

## 📋 Clinical Usage Examples

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

- **Clinical Boundaries**: The system is hard-coded to block diagnosis or prescription actions.
- **Human-in-the-loop**: Sensitive actions (like submitting Prior Auth) require explicit human approval.
- **Audit Trails**: All actions are logged to `audit_log.json` for HIPAA compliance foundations.
- **Response Sanitization**: All LLM outputs pass through a safety layer to ensure appropriate clinical language.

## 🧪 Testing
```bash
python -m pytest tests/ -v
```

## ⚖️ Regulatory Notes

Buddi is designed as a **Clinical Decision Support (CDS)** tool. It is not intended to replace professional medical judgment. 
- **HIPAA**: Foundation in place via audit logging. Production requires encryption at rest/transit.
- **FDA**: System avoids diagnosis/prescription territory to minimize regulatory risk under current FDA software guidance.
