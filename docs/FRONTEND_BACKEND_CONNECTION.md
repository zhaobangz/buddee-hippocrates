# Buddi API Integration Guide (Formerly Frontend-Backend Connection)

> **NOTICE**: The "Glassmorphic React Dashboard" and clinical chat frontend have been officially deprecated as of the RCM/Compliance pivot. Buddi now operates purely as an invisible API integration layer for enterprise health systems.

## 🏗 Architecture Overview

Buddi follows a **Decoupled API Model**:
- **Core Engine (API)**: A FastAPI Python server running on **port 8001** (`backend/api.py`). It manages agent orchestration, RCM shadow-mode analysis, QA auditing, and safety validation.
- **Enterprise Integration (EHR/Redox)**: Systems send clinical notes and encounter data securely to Buddi for asynchronous processing.

## 🛰 Communication Flow

EHR clients and middleware interact exclusively via **RESTful JSON payloads**.

### API Configuration
```javascript
const API_BASE_URL = 'http://localhost:8001/api';
```

### Communication Modes

| Mode | Endpoint | Description |
| :--- | :--- | :--- |
| **Task Processing** | `POST /process` | Handles `shadow_mode_rcm`, `specialty_prior_auth`, or `retrospective_qa_audit` tasks. Returns algorithmic assessments with cryptographic audit signatures. |
| **Status Monitor** | `GET /health` | Real-time health monitor ensuring safety layers are active. |
| **Patient Intel (Sync)** | `POST /patient` | Endpoint for pushing patient demographics / history during active encounter audits. |
| **Audit Compliance** | `GET /audit` | Secure endpoint for fetching the cryptographic trails of recent processing actions. |

## 🔓 EHR Integration Pathway

Buddi is designed for **Bidirectional EHR Integration**, typically facilitated by middle layers like **Redox** or **Health Gorilla**. 
The system does not require clinicians to open new tabs. It reads documentation asynchronously (Shadow Mode) and writes back suggested codes or flags directly using the facility's FHIR specifications.

## 🚀 Establishing the Service

Use the launcher to start the integration API:
```bash
python start.py
```

## 🔍 Troubleshooting

| Pulse | Cause | Prescription |
| :--- | :--- | :--- |
| **Offline** | Backend crashed | Ensure Python 3.9+ and pip dependencies are installed. |
| **Unrecognized Task** | Bad Payload | Ensure `task_type` is one of the supported intents (e.g. `shadow_mode_rcm`). |
