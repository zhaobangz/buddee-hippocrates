# Buddi Clinical Agent - Troubleshooting Guide

Critical solutions for healthcare terminal environment and clinical workflow issues.

## 🧠 Environment & Startup Issues

### ❌ Issue: `UnboundLocalError: local variable 'module'...` (Uvicorn)
- **Problem**: Corrupted system-level `uvicorn` or `importlib` in the global Python path (common in miniconda/system envs).
- **Prognosis**: Fatal startup failure.
- **Prescription**: **Use the Virtual Environment Guardian**. Ensure you are using `./run-web.sh` from the root. It is hard-coded to bypass system corruption by prioritizing the project-local `./venv`. If errors persist:
  ```bash
  rm -rf venv
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

### ❌ Issue: `ModuleNotFoundError: faiss` or `sentence_transformers`
- **Problem**: Missing dependencies for the Clinical RAG (Retrieval-Augmented Generation) engine.
- **Prescription**: Sync the AI terminal dependencies:
  ```bash
  ./venv/bin/pip install faiss-cpu sentence-transformers numpy scikit-learn
  ```

### ❌ Issue: `[Errno 48] Address already in use` (Port 8000)
- **Problem**: A previous backend instance (or uvicorn reloader) is still occupying port 8000.
- **Prescription**: Use the automated port-clearing built into the launcher, or manually flush the port:
  ```bash
  lsof -ti:8000 | xargs kill -9 2>/dev/null || true
  ```

## 🏥 Clinical Dashboard Issues

### ❌ Issue: "API Offline" in the Workspace
- **Problem**: Backend FastAPI pulse is not detected by the frontend terminal.
- **Prescription**:
  1. Verify the API is online via `curl http://localhost:8000/api/health`.
  2. Ensure your terminal browser matches the terminal server (Port 3000).
  3. Reference [FRONTEND_BACKEND_CONNECTION.md](FRONTEND_BACKEND_CONNECTION.md) for endpoint mapping.

### ❌ Issue: OCR or Audio capture fails
- **Problem**: Missing system-level binary dependencies on macOS.
- **Prescription**:
  ```bash
  brew install tesseract portaudio ffmpeg faiss
  ```

### ❌ Issue: `Permission denied: ./run-web.sh`
- **Problem**: The launcher script lacks execution bits.
- **Prescription**:
  ```bash
  chmod +x run-web.sh
  ```

---

**Clinical Support**: If your problem persists, check the detailed trace in the backend terminal or review the foundation logs at `audit_log.json`.
