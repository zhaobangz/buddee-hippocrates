#!/bin/bash

# Buddi Agent - Web Interface Launcher
# Starts both the FastAPI backend and web frontend

set -e

echo "=========================================="
echo "   Buddi Agent - Web Interface"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if uvicorn is installed
if ! python3 -c "import uvicorn" 2>/dev/null; then
    echo "Installing required packages..."
    pip install fastapi uvicorn[standard]
fi

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo "Shutting down servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "✓ Servers stopped"
}

trap cleanup EXIT

# Start backend
echo "Starting backend (FastAPI)..."
python3 -m uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo -e "${GREEN}✓ Backend PID: $BACKEND_PID${NC}"

# Give backend time to start
sleep 2

# Check if backend started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "❌ Failed to start backend"
    exit 1
fi

# Start frontend
echo ""
echo "Starting frontend (Web Server)..."
cd "$(dirname "$0")/web"
python3 -m http.server 5000 &
FRONTEND_PID=$!
echo -e "${GREEN}✓ Frontend PID: $FRONTEND_PID${NC}"

# Give frontend time to start
sleep 1

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Both servers are running!${NC}"
echo "=========================================="
echo ""
echo -e "${BLUE}Backend API:${NC}"
echo "  URL: http://localhost:8000"
echo "  Docs: http://localhost:8000/docs"
echo ""
echo -e "${BLUE}Frontend Web UI:${NC}"
echo "  URL: http://localhost:5000"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all servers${NC}"
echo ""

# Wait for both processes
wait
