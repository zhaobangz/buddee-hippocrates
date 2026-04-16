# Buddi Clinical Agent - Web Interface Setup Guide

This guide details the setup process for the Buddi Clinical Agent web terminal. The system uses a high-performance client-server architecture designed for medical grade stability and real-time clinical workflows.

## 🏗 Architecture Overview

- **Backend**: FastAPI server (`backend/api.py`) running on `localhost:8001`.
- **Frontend**: Vite-powered React UI (`frontend/`) running on `localhost:5173`.
- **Core AI**: Agentic orchestrator with RAG grounding and Secure Memory.

## 📁 Directory Structure

```
buddi/
├── backend/            # FastAPI REST API (Integrated Logic)
├── frontend/           # Premium React Dashboard (Vite)
├── core/               # RAG Engine, Memory, and Safety Layers
├── tools/              # Clinical workflows (Prior Auth, EHR, etc.)
├── venv/               # Isolated Project Environment
├── start.py            # Unified system launcher
└── requirements.txt    # Modern clinical AI dependencies
```

## 🚀 Setup Instructions

### 1. Isolated Virtual Environment (Mandatory)
To avoid library version conflicts (e.g., `uvicorn` corruption in system paths), you **must** use a local virtual environment:

```bash
# Create the environment
python3 -m venv venv
source venv/bin/activate

# Install healthcare AI, web, and medical libraries
pip install -r requirements.txt

# macOS only: Essential system tools for FAISS stability
brew install faiss
```

### 2. Frontend Dependencies
Install the Node.js dependencies for the modern dashboard:

```bash
cd frontend
npm install
cd ..
```

### 3. Configure Environment
Add your LLM provider credentials to the environment file:

```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY / LLM_PROVIDER
```

### 4. Launch the Terminal
The automated launcher starts both the Backend and Frontend with **Environment Protection**:

```bash
python start.py
```

- **Web Dashboard**: [http://localhost:5173](http://localhost:5173)
- **Backend API**: [http://localhost:8001](http://localhost:8001)
- **Interactive Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)

## 📡 Using the Terminal

1. **Patient Context**: Set demographics and condition lists to activate the **Context Sidebar**. This is done via the **👤 Demo** button or directly via POST `/api/patient`.
2. **Tab Switching**: Use the header navigation to toggle between **Chat**, **Risk Dashboard** (Heatmap), and **Shadow Mode**.
3. **Workflow Triggers**: Click the teal workflow icons (⚠️, 🕰️, 📋) to quickly execute common clinical tasks like risk assessment, history recall, and prior auth generation.
4. **Shadow Mode**: Compare agent suggestions against expert baselines to validate clinical reasoning.

## 🛠 Troubleshooting

- **⚠️ Address Already in Use**: If you get Errno 48 (port 8001 or 5173), ensure no other instances of `uvicorn` or `npm` are running.
- **❌ Missing Dependencies**: If the RAG engine fails to load, ensure `faiss-cpu`, `sentence-transformers`, and `numpy` were installed in the active `venv`.
- **🔑 API Key Error**: Ensure `LLM_API_KEY` is correctly set in your `.env` file and that you've restarted the launcher.

---

**Ready for Clinical Production.** Reference [FRONTEND_BACKEND_CONNECTION.md](FRONTEND_BACKEND_CONNECTION.md) for more details on the REST integration.

