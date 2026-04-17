# Buddi RCM & Compliance AI

> **Invisible Revenue Integrity and Compliance Auditing**

Buddi is an enterprise-grade AI engine designed for Revenue Cycle Management (RCM) and compliance auditing. Abandoning the "swiss army knife" approach to clinical assistance, Buddi focuses exclusively on high-ROI, low-friction, backend integrations.

## 🎯 Core Capabilities
1. **Shadow Mode Revenue Integrity**: Runs invisibly on post-visit charts. Compares physician notes against billed codes to flag missed HCC (Hierarchical Condition Category) codes and recover revenue immediately.
2. **Specialty-Specific Prior Auth**: Hyper-focused prior authorization engine tailored for high-friction workflows like Oncology step-therapy and GI biologics.
3. **Retrospective QA Auditor**: Automated auditing of random clinical charts for adherence to established clinical guidelines, securely backed by RAG.
4. **Cryptographic Audit Trail**: Every automated action, prompt, and RAG retrieval is cryptographically tracked to provide complete algorithmic transparency and liability protection for compliance teams.
5. **EHR Integration Ready**: Designed strictly for backend API integration (e.g., through Redox / Health Gorilla), operating transparently without a separate clinician dashboard.

## 🏗 Lean Architecture
- **Backend API**: FastAPI (Python) - Secure integration endpoint.
- **Engine**: Intent-Driven Orchestrator with FAISS-based RAG grounding.

## 🚀 Quick Start

### 1. Prerequisites
- **Python**: 3.9 or higher
- **Homebrew (macOS)**: `brew install faiss` (recommended for RAG stability)

### 2. Installation
```bash
# Clone the repository and enter the directory
cd buddi

# Setup Python Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure Environment
cp .env.example .env
# Edit .env with your LLM_API_KEY
```

### 3. Launching the System
The launcher starts the FastAPI backend:
```bash
python start.py
```

- **API (Direct)**: [http://localhost:8001](http://localhost:8001)
- **Interactive API Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)

## 📁 Repository Structure
```
buddi/
├── backend/            # Consolidated Production API (v3.1)
├── core/               # LLM Orchestrator, RAG, and Memory
├── tools/              # Clinical workflow implementations
├── docs/               # Detailed documentation and guides
└── start.py            # API launcher
```

## 🛡 Safety & Compliance
- **Guardrails**: Complete focus on retrospective and administrative tasks.
- **Audit**: Every action is cryptographically tracked in `audit_log.json`.
- **SaMD Exclusion**: Complies with FDA Jan 2026 update by providing full algorithmic transparency and not functioning as a medical device.