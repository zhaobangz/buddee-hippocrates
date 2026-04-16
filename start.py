#!/usr/bin/env python3
"""
Buddi Unified Launcher v3.1
Starts the optimized clinical system (FastAPI + Vite) with correct PYTHONPATH
"""
import subprocess
import time
import sys
import os
import signal

def start():
    print("🚀 Initializing Buddi Clinical v3.1...")
    
    # Set PYTHONPATH to include current directory
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{os.getcwd()}:{env.get('PYTHONPATH', '')}"
    
    # 1. Start FastAPI Backend (Port 8001)
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8001"],
        env=env,
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.STDOUT
    )
    
    # 2. Start Frontend (Vite)
    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="frontend",
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.STDOUT
    )
    
    print("✅ System Online")
    print("   - API:      http://localhost:8001")
    print("   - Terminal: http://localhost:5173")
    print("\nPress Ctrl+C to terminate all services.")
    
    try:
        while True:
            time.sleep(2)
            if backend.poll() is not None:
                print("Backend process died. Check logs.")
                break
            if frontend.poll() is not None:
                print("Frontend process died. Check logs.")
                break
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        backend.terminate()
        frontend.terminate()

if __name__ == "__main__":
    start()
