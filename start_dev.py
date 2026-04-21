#!/usr/bin/env python3
"""
Buddi local development launcher.

This is the ONLY place `--reload` is permitted (per Track 1 / Step 1,
CFG-05). It boots the canonical backend (`backend.api:app` on port 8001) with
auto-reload enabled, and — if the `frontend/` directory exists — also boots
the Vite dev server.

Do NOT use this in production or CI. `start.py` is the production entry
point; `docker compose up` is the staging entry point.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import List, Optional


DEV_HOST = os.environ.get("HOST", "127.0.0.1")
DEV_PORT = int(os.environ.get("PORT", "8001"))


def _banner() -> None:
    print("🧪  Buddi DEV launcher")
    print(f"    Backend:  http://{DEV_HOST}:{DEV_PORT}  (backend.api:app, --reload ON)")
    print( "    Frontend: http://localhost:5173        (Vite, if frontend/ present)")
    print( "    Press Ctrl+C to terminate.")


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{os.getcwd()}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env.setdefault("DEV_MODE", "true")

    backend_cmd: List[str] = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.api:app",
        "--host",
        DEV_HOST,
        "--port",
        str(DEV_PORT),
        "--reload",
    ]

    _banner()
    backend = subprocess.Popen(backend_cmd, env=env)

    frontend: Optional[subprocess.Popen] = None
    if os.path.isdir("frontend"):
        # Surface the canonical backend URL to Vite via its standard env var.
        fe_env = env.copy()
        fe_env.setdefault("VITE_API_BASE", f"http://{DEV_HOST}:{DEV_PORT}/api")
        frontend = subprocess.Popen(["npm", "run", "dev"], cwd="frontend", env=fe_env)
    else:
        print("[start_dev.py] ⚠️  frontend/ not found; backend only.")

    procs = [p for p in (backend, frontend) if p is not None]

    def _terminate(signum=None, _frame=None):
        print("\n[start_dev.py] 🛑  Shutting down…")
        for p in procs:
            try:
                p.terminate()
            except ProcessLookupError:
                pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: _terminate(s, f))

    try:
        while True:
            time.sleep(1)
            for p in procs:
                if p.poll() is not None:
                    print(f"[start_dev.py] process exited (pid={p.pid}, rc={p.returncode}).")
                    _terminate()
                    return p.returncode or 1
    except KeyboardInterrupt:
        _terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
