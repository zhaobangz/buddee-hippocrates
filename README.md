# Buddi Clinical Agent 

> **High-impact Healthcare Workflow Intelligence**

Buddi is a lean, high-performance clinical decision support system designed for speed, clarity, and clinician value. It integrates real-time RAG (Retrieval-Augmented Generation), patient risk assessment, and workflow automation into a premium glassmorphic dashboard.

## 🎯 Core Capabilities
1. **AI Clinical Chat**: RAG-powered decision support grounded in medical guidelines.
2. **Patient Intelligence**: Automated profile summaries covering demographics, risks, and medical history.
3. **Risk Dashboard**: Visual heatmap of patient severity for rapid prioritization.
4. **Workflow Automation**: One-click Prior Authorization and Scheduling orchestration.
5. **Shadow Mode**: Side-by-side validation of agent intent vs. expert baseline for QA.
6. **Audit Trail**: Every action is cryptographically tracked for HIPAA foundations.

## 🏗 Lean Architecture
- **Frontend**: React + Vite + Tailwind (Modern Clinical Terminal)
- **Backend**: FastAPI (Consolidated Service Registry with OpenTelemetry Tracing)
- **Engine**: Intent-Driven Orchestrator with FAISS-based RAG grounding.

## 🚀 Quick Start

### 1. Prerequisites
- **Python**: 3.9 or higher
- **Node.js**: 18.x or higher
- **Homebrew (macOS)**: `brew install faiss` (recommended for RAG stability)

### 2. Installation
```bash
# Clone the repository and enter the directory
cd buddi

# Setup Python Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup Frontend Dependencies
cd frontend
npm install
cd ..

# Configure Environment
cp .env.example .env
# Edit .env with your LLM_API_KEY
```

### 3. Launching the System
The unified launcher starts both the FastAPI backend and the Vite frontend:
```bash
python start.py
```

- **Dashboard**: [http://localhost:5173](http://localhost:5173)
- **API (Direct)**: [http://localhost:8001](http://localhost:8001)
- **Interactive API Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)

## 📁 Repository Structure
```
buddi/
├── app/                # Modular Backend (Under Development)
├── backend/            # Consolidated Production API (v3.1)
├── frontend/           # Vite-powered React Dashboard
├── core/               # LLM Orchestrator, RAG, and Memory
├── tools/              # Clinical workflow implementations
├── docs/               # Detailed documentation and guides
└── start.py            # Unified system launcher
```

## 🛡 Safety & Compliance
- **Guardrails**: Hard-coded blocking of diagnosis/prescription actions.
- **CDS**: Buddi is a Clinical Decision Support tool, not a medical provider.
- **Audit**: Every action is cryptographically tracked in `audit_log.json`.

---
Buddi is designed for Staff Engineers to build on and Clinicians to actually use.