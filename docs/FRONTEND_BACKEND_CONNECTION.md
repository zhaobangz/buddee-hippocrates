# Buddi Clinical Agent — Frontend-Backend Connection Guide

This guide details the architectural link between the Buddi Clinical Agent's high-premium web terminal and its healthcare-AI backend. The connection uses a decoupled REST framework for high visibility and reliable scaling.

## 🏗 Architecture Overview

Buddi follows a **Decoupled Workflow Model**:
- **Backend (API)**: A FastAPI Python server running on **port 8000** (`backend/api.py`). It manages agent orchestration, clinical RAG, and safety validation.
- **Frontend (Terminal)**: A vanilla ES6 JavaScript/HTML5 application served via a Python-based HTTP server on **port 3000** (`web/`).

## 🛰 Communication Flow

The frontend and backend interact exclusively via **RESTful JSON payloads**.

### 1. API Configuration
The connection is established in `web/script.js` via a deterministic base URL:
```javascript
const API_BASE_URL = 'http://localhost:8000/api';
```

### 2. Communication Modes

| Mode | Endpoint | Description |
| :--- | :--- | :--- |
| **Chat** | `POST /chat` | Standard clinical query handling (EHR parsing, Guidelines, etc.). |
| **Status** | `GET /status` | Real-time health monitor for Memory, Healthcare Tools, and Safety Layers. |
| **Risk Dashboard** | `GET /risk-assessment` | Returns structured JSON data for the interactive risk heatmap. |
| **Shadow Mode** | `POST /shadow-mode/compare` | Compares AI intent vs. expert baseline for clinical validation. |
| **Context** | `GET /patient-context` | Fetches demographics and conditions for the sidebar terminal. |

## 🔓 CORS (Cross-Origin Resource Sharing)

Buddi is pre-configured to handle cross-origin requests between the development server (3000) and the API (8000). The backend in `backend/api.py` includes **CORS Middleware** by default.

## 🚀 Establishing the Pulse

Use the **Absolute-Path Launcher** to establish the primary connection:
```bash
# Recommended for local development and clinical testing
chmod +x run-web.sh
./run-web.sh
```

## 🔍 Connection Troubleshooting

| Pulse | Cause | Prescription |
| :--- | :--- | :--- |
| **Flatline (API Offline)** | Backend crashed or uninitialized | Check for the `./venv` and ensure `run-web.sh` is active. |
| **Arrhythmia (404/Not Found)** | Endpoint mismatch | Verify that the route defined in `backend/api.py` matches `script.js`. |
| **Blocked (CORS Error)** | Port 8000 conflict | Port 8000 might be locked by an orphaned process. Use `kill -9 $(lsof -ti:8000)`. |
| **Delayed Response** | Heavy RAG/Model loading | The RAG engine (Sentence-Transformers) may take 10-20sec to load on first launch. |

## 🛠 Adding New Clinical Circuits

To add a new feature (e.g., "Patient Labs"):
1.  **Backend**: Define a route in `backend/api.py` (e.g., `@app.get("/api/labs")`).
2.  **Frontend**: Create a handler in `web/script.js` (e.g., `async fetchLabs()`).
3.  **UI/UX**: Update the **Tab View** in `web/index.html` to visualize the laboratory data.

---

**Connection Status**: ✅ **Synchronized**. The Buddi terminal is fully mapped to the healthcare-AI core.
