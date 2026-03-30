# Buddi Clinical Agent - Web Interface Setup Guide

This guide details the setup process for the Buddi Clinical Agent web terminal. The system uses a high-performance client-server architecture designed for medical grade stability and real-time clinical workflows.

## 🏗 Architecture Overview

- **Backend**: FastAPI server (`backend/api.py`) running on `localhost:8000`.
- **Frontend**: Static Web UI (`web/`) served on `localhost:3000`.
- **Core AI**: Agentic orchestrator with RAG grounding and Secure Memory.
- **Perception**: Integrated Audio/OCR via Python-based widget services.

## 📁 Directory Structure

```
buddi/
├── backend/            # FastAPI REST API (Logic orchestration)
├── web/                # Premium Web Dashboard (HTML/CSS/JS)
├── core/               # RAG Engine, Memory, and Safety Layers
├── tools/              # Clinical workflows (Prior Auth, EHR, etc.)
├── venv/               # Isolated Project Environment
├── run-web.sh          # Primary absolute-path server launcher
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

# macOS only: Essential system tools for OCR and Audio
brew install tesseract portaudio ffmpeg faiss
```

### 2. Configure Environment
Add your LLM provider credentials to the environment file:

```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY / LLM_PROVIDER
```

### 3. Launch the Terminal
The automated launcher starts both the Backend and Frontend with **Environment Protection**:

```bash
chmod +x run-web.sh
./run-web.sh
```

- **Web Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

## 📡 Using the Terminal

1. **Patient Context**: Set demographics and condition lists to activate the **Context Sidebar**.
2. **Tab Switching**: Use the header navigation to toggle between **Chat**, **Risk Dashboard** (Heatmap), and **Shadow Mode**.
3. **Perception Control**: Clicking the Siri-inspired mic icon or the screen scan icons in the chat input will trigger background OCR and audio capture.
4. **Workflow Triggers**: Click the teal workflow icons (⚠️, 🕰️, 📋) to quickly execute common clinical tasks.

## 🛠 Troubleshooting

- **⚠️ Address Already in Use**: If you get Errno 48 (port 8000), `run-web.sh` will automatically attempt to kill the previous instance. If it persists, run `lsof -ti:8000 | xargs kill -9`.
- **❌ Missing Dependencies**: If the RAG engine fails to load, ensure `faiss-cpu`, `sentence-transformers`, and `numpy` were installed in the active `venv`.
- **🎙️ Audio Perms**: On macOS, ensure your terminal has "Microphone" and "Screen Recording" permissions enabled in **System Settings -> Privacy & Security**.

---

**Ready for Clinical Production.** Reference [FRONTEND_BACKEND_CONNECTION.md](FRONTEND_BACKEND_CONNECTION.md) for more details on the REST integration.
