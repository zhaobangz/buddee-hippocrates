#!/bin/bash

# Buddi Agent - Web Interface Development Launcher
# Starts both servers with hot-reload and better logging

set -e

echo "=========================================="
echo "   Buddi Agent - Web Interface (Dev Mode)"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=8000
FRONTEND_PORT=3000
BACKEND_LOG="logs/backend.log"
FRONTEND_LOG="logs/frontend.log"

# Create logs directory
mkdir -p logs

echo "Configuration:"
echo "  Backend:  http://localhost:$BACKEND_PORT"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed or not in PATH${NC}"
    exit 1
fi

# Check if required packages are installed
echo "Checking dependencies..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "Installing required packages..."
    pip install fastapi uvicorn[standard]
fi
echo -e "${GREEN}✓ Dependencies OK${NC}"

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down servers...${NC}"
    
    if [ ! -z "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID 2>/dev/null || true
        echo -e "${GREEN}✓ Backend stopped${NC}"
    fi
    
    if [ ! -z "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID 2>/dev/null || true
        echo -e "${GREEN}✓ Frontend stopped${NC}"
    fi
}

trap cleanup EXIT

# Start backend
echo ""
echo -e "${BLUE}Starting backend (FastAPI with hot-reload)...${NC}"
python3 -m uvicorn backend.api:app --reload --host 0.0.0.0 --port $BACKEND_PORT > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# Start frontend
echo -e "${BLUE}Starting frontend (Web Server)...${NC}"
cd "$(dirname "$0")/web"
python3 -m http.server $FRONTEND_PORT > "../$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

# Wait for servers to start
sleep 2

# Check if both started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}❌ Backend failed to start${NC}"
    echo "Error log:"
    cat "../$BACKEND_LOG"
    exit 1
fi

if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${RED}❌ Frontend failed to start${NC}"
    echo "Error log:"
    cat "../$FRONTEND_LOG"
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Development servers running!${NC}"
echo "=========================================="
echo ""
echo -e "${BLUE}Backend API:${NC}"
echo "  URL: http://localhost:$BACKEND_PORT"
echo "  Docs: http://localhost:$BACKEND_PORT/docs"
echo "  Log: tail -f $BACKEND_LOG"
echo ""
echo -e "${BLUE}Frontend Web UI:${NC}"
echo "  URL: http://localhost:$FRONTEND_PORT"
echo "  Log: tail -f $FRONTEND_LOG"
echo ""
echo -e "${YELLOW}Tips:${NC}"
echo "  - Backend auto-reloads on Python changes"
echo "  - Frontend auto-reloads on browser refresh"
echo "  - View API docs at http://localhost:$BACKEND_PORT/docs"
echo "  - Press Ctrl+C to stop all servers"
echo ""

# Tail logs
echo "Output streams:"
echo ""
( tail -f "../$BACKEND_LOG" & 
  BACKEND_TAIL=$!
  tail -f "../$FRONTEND_LOG" &
  FRONTEND_TAIL=$!
  
  wait
)

# If we get here, wait for main processes
wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
