# Buddi Agent Web Interface - Setup & Deployment Guide

This guide explains how to set up and run your Buddi Agent with a web interface locally. The architecture is cloud-ready for easy migration to AWS, Google Cloud, or Azure later.

## Architecture Overview

Your application is now structured as a **client-server architecture**:

- **Backend**: FastAPI server running on `localhost:8000` (can be deployed to cloud)
- **Frontend**: Web UI served from `localhost:5000` (can be deployed to CDN or same server)
- **Agent Core**: Your existing AI agent logic (runs on backend)

This separation allows you to:
1. Run everything locally for development
2. Deploy individually to cloud services
3. Scale independently
4. Use different hosting for each component

## Directory Structure

```
buddi/
├── backend/
│   ├── __init__.py
│   └── api.py              # FastAPI backend
├── web/
│   ├── index.html          # Web UI
│   ├── style.css           # Styling
│   └── script.js           # Frontend logic
├── core/                   # Your existing agent logic
├── tools/                  # Your existing tools
├── config/                 # Your existing config
├── main.py                 # Original CLI entry point
└── requirements.txt        # Updated with FastAPI & uvicorn
```

## Prerequisites

- Python 3.9+ (you likely have this already)
- Conda or pip
- A modern web browser

## Setup Instructions

### 1. Install Dependencies

First, update your requirements and install the new packages:

```bash
pip install fastapi uvicorn[standard] python-dotenv
```

Or if you want to reinstall everything from requirements.txt:

```bash
pip install -r requirements.txt
```

If you use conda (recommended):

```bash
conda install fastapi uvicorn python-dotenv
```

### 2. Run the Backend (API Server)

Open a terminal and run:

```bash
python -m uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

The API is now running at: http://localhost:8000

Check the API docs at: http://localhost:8000/docs

### 3. Run the Frontend (Web UI)

Open **another terminal** and serve the web files:

**Option A: Using Python (Simple)**
```bash
cd web
python -m http.server 5000
```

**Option B: Using Node.js http-server (if installed)**
```bash
cd web
npx http-server -p 5000
```

**Option C: Using Python Flask (More robust)**
```bash
pip install flask
python -c "from flask import Flask; app = Flask('buddi', static_folder='.', static_url_path=''); app.run(port=5000)"
```

You should see output indicating the server is running on port 5000.

### 4. Open the Web Interface

Open your browser and go to:
```
http://localhost:5000
```

You should see the Buddi Agent web interface!

## Running Both Frontend and Backend Together

To make development easier, you can create a simple script:

**macOS/Linux: `run-web.sh`**
```bash
#!/bin/bash

# Start backend
echo "Starting backend..."
python -m uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend..."
cd web
python -m http.server 5000 &
FRONTEND_PID=$!

echo ""
echo "✓ Backend running at http://localhost:8000"
echo "✓ Frontend running at http://localhost:5000"
echo "Press Ctrl+C to stop both servers"

# Handle cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID" EXIT

wait
```

**Windows: `run-web.bat`**
```batch
@echo off
echo Starting Buddi Agent Web Interface...

start cmd /k "python -m uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000"
echo Backend started on http://localhost:8000

cd web
start cmd /k "python -m http.server 5000"
echo Frontend started on http://localhost:5000

echo.
echo Both servers are running. Open http://localhost:5000 in your browser
```

Make the scripts executable:
```bash
chmod +x run-web.sh
./run-web.sh
```

## Testing the Setup

### Test Backend Health
```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{"status": "healthy", "service": "buddi-agent-api"}
```

### Test Agent Status
```bash
curl http://localhost:8000/api/status
```

### Test Chat (send a message)
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how are you?", "include_history": false}'
```

## Implementing Agent Processing

The backend is currently set up but needs your actual agent logic connected. In `backend/api.py`, find the `process_user_input()` function and implement it:

```python
async def process_user_input(user_input: str) -> str:
    """Process user input through the agent"""
    
    if agent is None:
        return "Agent not initialized"
    
    # TODO: Implement based on your Agent class
    # Example options:
    
    # Option 1: If your agent has a process() method
    # response = agent.process(user_input)
    
    # Option 2: If your agent has a chat() method
    # response = agent.chat(user_input)
    
    # Option 3: If you need to detect intent first
    # intent = agent.detect_intent(user_input)
    # response = agent.handle_intent(intent, user_input)
    
    return response
```

Check your `core/agent.py` to see what methods are available to call.

## Preparing for Cloud Deployment

When you're ready to move to AWS/Google Cloud/Azure, your architecture is ready:

### AWS Deployment
- **Backend**: Deploy to AWS EC2, Lambda, or AppRunner
- **Frontend**: Deploy to S3 + CloudFront
- **Database** (if needed): AWS RDS or DynamoDB

### Google Cloud
- **Backend**: Deploy to Cloud Run
- **Frontend**: Deploy to Firebase Hosting or Cloud Storage + CDN
- **Database**: Cloud Firestore or Cloud SQL

### Azure
- **Backend**: Deploy to App Service or Container Instances
- **Frontend**: Deploy to Static Web Apps
- **Database**: Azure SQL or Cosmos DB

### Key Changes Needed for Cloud:
1. Update `API_BASE_URL` in `web/script.js` to your cloud endpoint
2. Update CORS settings in `backend/api.py` to allow your domain
3. Add environment variables for API keys, credentials, etc.
4. Use containerization (Docker) for consistency

## Docker Setup (Optional, but recommended for cloud migration)

Your `Dockerfile` and `docker-compose.yml` are already in place. To run with Docker:

```bash
docker-compose up
```

This will run both the backend and serve the frontend through Docker.

## Troubleshooting

### CORS Errors in Browser Console
- Check that backend is running on port 8000
- Check that frontend is running on port 5000
- If deploying, update `allow_origins` in `backend/api.py`

### Frontend Can't Connect to API
- Check `API_BASE_URL` in `web/script.js` matches your backend URL
- Ensure backend is running: `curl http://localhost:8000/api/health`

### Agent Not Responding
- Check the agent initialization in `backend/api.py` startup event
- Check that your agent logic is correctly connected in `process_user_input()`
- Check logs in the backend terminal

### Port Already in Use
- Change port in commands: `uvicorn ... --port 8001`
- Update frontend to connect to new port in `web/script.js`

## Next Steps

1. **Connect your agent logic**: Implement `process_user_input()` in `backend/api.py`
2. **Test locally**: Verify the web UI works and can interact with your agent
3. **Add more API endpoints**: Create endpoints for specific agent features (web search, file operations, etc.)
4. **Implement database**: Add a database for chat history, user sessions, etc.
5. **Deploy to cloud**: When ready, deploy to AWS/Google Cloud/Azure

## Resources

- FastAPI Docs: https://fastapi.tiangolo.com/
- Uvicorn: https://www.uvicorn.org/
- Docker for deployment: https://docs.docker.com/
- Cloud deployment guides: [See cloud provider docs]

---

**Status**: Local development ready. Cloud deployment ready (structure in place).
