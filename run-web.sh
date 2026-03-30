#!/bin/bash

# Buddi Agent - Web Interface Launcher
# Starts both the FastAPI backend and web frontend

set -e

# Change to the directory of the script
cd "$(dirname "$0")"
PROJECT_ROOT="$PWD"

echo "=========================================="
echo "   Buddi Agent - Web Interface"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Find the best Python interpreter
if [ -f "$PROJECT_ROOT/venv/bin/python3" ]; then
    PYTHON_CMD="$PROJECT_ROOT/venv/bin/python3"
    echo -e "${BLUE}Using local venv: $PYTHON_CMD${NC}"
else
    PYTHON_CMD="python3"
    echo -e "${YELLOW}Warning: venv not found. Using system python3${NC}"
fi

# Check if Python is available
if ! command -v "$PYTHON_CMD" &> /dev/null; then
    echo "❌ Python is not installed or not in PATH"
    exit 1
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
# Force-clear port 8000 to prevent 'Address already in use' errors on macOS
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
"$PYTHON_CMD" -m uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo -e "${GREEN}✓ Backend PID: $BACKEND_PID${NC}"

# Give backend time to start
sleep 3

# Check if backend started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "❌ Failed to start backend"
    exit 1
fi

# Start frontend
echo ""
echo "Starting frontend (Web Server)..."
# Use a subshell to start the frontend so we don't change the current directory permanently
(
    cd "$PROJECT_ROOT/web"
    "$PYTHON_CMD" -m http.server 3000 &
    echo $! > "$PROJECT_ROOT/frontend.pid"
)
FRONTEND_PID=$(cat "$PROJECT_ROOT/frontend.pid")
rm "$PROJECT_ROOT/frontend.pid"
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
echo "  URL: http://localhost:3000"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all servers${NC}"
echo ""

# Wait for both processes
wait
