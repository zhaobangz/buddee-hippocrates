#!/usr/bin/env python3
"""
Buddi Unified Launcher v4.1
Starts the optimized clinical system (FastAPI + Vite) with correct PYTHONPATH
"""
import subprocess
import time
import sys
import os
import signal

def start():
    print("🚀 Initializing Buddi Clinical Agent v4.1...")
    
    # Set PYTHONPATH to include current directory
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{os.getcwd()}:{env.get('PYTHONPATH', '')}"
    
    # 1. Start FastAPI Backend (Port 8001)
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8001", "--reload"],
        env=env,
    )
    
    # 2. Start Frontend (Vite)
    # Check if frontend directory exists before starting
    if os.path.exists("frontend"):
        print("📦 Starting Frontend (Vite)...")
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd="frontend",
        )
    else:
        print("⚠️ Frontend directory not found. Skipping frontend startup.")
        frontend = None
    
    print("\n✅ System Online")
    print("   - Backend API: http://localhost:8001")
    if frontend:
        print("   - Terminal UI: http://localhost:5173")
    print("\nPress Ctrl+C to terminate all services.")
    
    try:
        while True:
            time.sleep(2)
            if backend.poll() is not None:
                print("Backend process died. Check logs.")
                break
            if frontend and frontend.poll() is not None:
                print("Frontend process died. Check logs.")
                break
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        backend.terminate()
        if frontend:
            frontend.terminate()

if __name__ == "__main__":
    start()
