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
    print("🚀 Initializing Buddi Clinical Agent Backend v1.0...")
    
    # Set PYTHONPATH to include current directory
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{os.getcwd()}:{env.get('PYTHONPATH', '')}"
    
    # Start FastAPI Backend (Port 8001)
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8001", "--reload"],
        env=env,
    )
    
    print("✅ Backend Online")
    print("   - API: http://localhost:8001")
    print("   - Health: http://localhost:8001/api/health")
    print("\nPress Ctrl+C to terminate services.")
    
    try:
        while True:
            time.sleep(2)
            if backend.poll() is not None:
                print("Backend process died. Check logs.")
                break
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        backend.terminate()

if __name__ == "__main__":
    start()
