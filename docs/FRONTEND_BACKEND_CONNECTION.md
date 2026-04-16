# Buddi Clinical Agent — Frontend-Backend Connection Guide

This guide details the architectural link between the Buddi Clinical Agent's high-premium web terminal and its healthcare-AI backend. The connection uses a decoupled REST framework for high visibility and reliable scaling.

## 🏗 Architecture Overview

Buddi follows a **Decoupled Workflow Model**:
- **Backend (API)**: A FastAPI Python server running on **port 8001** (`backend/api.py`). It manages agent orchestration, clinical RAG, and safety validation.
- **Frontend (Terminal)**: A Vite-powered React application running on **port 5173** (`frontend/`).

## 🛰 Communication Flow

The frontend and backend interact exclusively via **RESTful JSON payloads**.

### 1. API Configuration
The connection is established in the frontend (e.g., via environment variables or a shared config) pointing to:
```javascript
const API_BASE_URL = 'http://localhost:8001/api';
```

### 2. Communication Modes

| Mode | Endpoint | Description |
| :--- | :--- | :--- |
| **Chat** | `POST /chat` | Standard clinical query handling (EHR parsing, Guidelines, etc.). |
| **Status** | `GET /status` | Real-time health monitor for Memory, Healthcare Tools, and Safety Layers. |
| **Risk Dashboard** | `GET /risk` | Returns structured JSON data for the interactive risk heatmap. |
| **Patient Intel** | `GET /patient` | Fetches consolidated intelligence brief and interaction history. |
| **Shadow Mode** | `POST /shadow-mode/compare` | Compares AI intent vs. expert baseline for clinical validation. |
| **Audit Log** | `GET /audit` | Fetches recent safety and compliance events. |

## 🔓 CORS (Cross-Origin Resource Sharing)

Buddi is pre-configured to handle cross-origin requests between the Vite development server (5173) and the API (8001). The backend in `backend/api.py` includes **CORS Middleware** allowing all origins in development mode.

## 🚀 Establishing the Pulse

Use the **Unified Launcher** to establish the primary connection:
```bash
python start.py
```

## 🔍 Connection Troubleshooting

| Pulse | Cause | Prescription |
| :--- | :--- | :--- |
| **Flatline (API Offline)** | Backend crashed or uninitialized | Check for the `./venv` and ensure `start.py` is active. |
| **Arrhythmia (404/Not Found)** | Endpoint mismatch | Verify that the route defined in `backend/api.py` matches the frontend service calls. |
| **Blocked (CORS Error)** | Port 8001 conflict | Port 8001 might be locked by an orphaned process. Use `kill -9 $(lsof -ti:8001)`. |
| **Delayed Response** | Heavy RAG/Model loading | The RAG engine (Sentence-Transformers) may take 10-20sec to load on first launch. |

## 🛠 Adding New Clinical Circuits

To add a new feature (e.g., "Patient Labs"):
1.  **Backend**: Define a route in `backend/api.py` (e.g., `@app.get("/api/labs")`).
2.  **Frontend**: Create a service or hook in `frontend/src/` (e.g., `async fetchLabs()`).
3.  **UI/UX**: Update the relevant React component in `frontend/src/components/` to visualize the laboratory data.

---

**Connection Status**: ✅ **Synchronized**. The Buddi terminal is fully mapped to the healthcare-AI core.

