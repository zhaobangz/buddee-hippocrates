# Buddi Clinical Agent - Web Interface Setup Guide

This guide explains how to set up and run the Buddi Clinical Agent web interface. The system uses a client-server architecture designed for local development and cloud scalability.

## Architecture Overview

- **Backend**: FastAPI server (`backend/api.py`) running on `localhost:8000`.
- **Frontend**: Static Web UI (`web/`) served on `localhost:5000`.
- **Agent Core**: Specialized healthcare clinical agent logic.

## Directory Structure

```
buddi/
├── backend/
│   └── api.py              # FastAPI backend (Already connected to Agent)
├── web/
│   ├── index.html          # Web UI structure
│   ├── style.css           # Clinical-themed styling
│   └── script.js           # Frontend-Backend bridge
├── core/                   # Agent logic & medical safety layer
├── tools/                  # Healthcare-specific tools (EHR reader, Prior Auth, etc.)
├── run-web-dev.sh          # Recommended dev launcher
└── requirements.txt        # Full project dependencies
```

## Setup Instructions

### 1. Install Dependencies

Ensure you have Python 3.9+ and pip installed.

```bash
# Install all required Python packages
pip install -r requirements.txt

# macOS only: System-level tools for audio and OCR
brew install portaudio tesseract ffmpeg
```

### 2. Configure Environment

Copy the example environment file and add your LLM API credentials.

```bash
cp .env.example .env
# Edit .env and set LLM_API_KEY
```

### 3. Run the Development Environment

The easiest way to start both the backend and frontend together is using the development script:

```bash
chmod +x run-web-dev.sh
./run-web-dev.sh
```

- **Backend API**: http://localhost:8000
- **Web Interface**: http://localhost:5000
- **API Docs**: http://localhost:8000/docs

## Using the Web Interface

1. **Dashboard**: View the status of the Clinical Agent (Memory, Healthcare Tools, Safety Layer).
2. **Chat**: Interact with the agent to trigger clinical workflows.
3. **Audit Log**: Review recent clinical actions and safety validations.

### Example Commands to Try:
- "Load patient Jane Doe, ID 9876, asthma, on albuterol"
- "Search for latest ADA guidelines on type 2 diabetes"
- "Generate a prior auth for MRI Brain"
- "Create a follow-up for symptom check in 3 days"

## Troubleshooting

- **CORS Errors**: Ensure both servers are running. The backend is configured to allow requests from the local frontend by default.
- **API Offline**: Check that the backend terminal is still running and hasn't encountered initialization errors (e.g., missing API keys).
- **Tool Failures**: Some tools (like OCR or Audio) require the system-level homebrew dependencies mentioned in step 1.

## Cloud Deployment

The Buddi Clinical Agent is cloud-ready. For detailed instructions on deploying to AWS, GCP, or Azure, refer to [CLOUD_DEPLOYMENT_GUIDE.md](CLOUD_DEPLOYMENT_GUIDE.md).
