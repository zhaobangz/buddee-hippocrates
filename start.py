#!/usr/bin/env python3
"""
Buddi production launcher.

Track 1 / Step 1 (ARCH-01, CFG-01, CFG-05, DO-01): starts ONLY the canonical
API (`backend.api:app` on port 8001). `--reload` is explicitly forbidden here;
for the local dev loop use `start_dev.py` instead.

This launcher does not fork the frontend dev server — in production the
frontend is served as a static build by a separate web tier, and in CI/staging
`docker compose up` is the authoritative entry point.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import NoReturn


DEFAULT_HOST = "0.0.0.0"  # Container ingress / platform-managed network, not public
DEFAULT_PORT = 8001


def _fatal(msg: str, code: int = 1) -> NoReturn:
    print(f"[start.py] FATAL: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> int:
    if "--reload" in sys.argv:
        _fatal("--reload is not permitted in start.py. Use start_dev.py for dev.")

    host = os.environ.get("HOST", DEFAULT_HOST)
    try:
        port = int(os.environ.get("PORT", DEFAULT_PORT))
    except ValueError:
        _fatal(f"Invalid PORT env var: {os.environ.get('PORT')!r}")

    try:
        workers = int(os.environ.get("APP_WORKERS", "1"))
    except ValueError:
        _fatal(f"Invalid APP_WORKERS env var: {os.environ.get('APP_WORKERS')!r}")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{os.getcwd()}{os.pathsep}{env.get('PYTHONPATH', '')}"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.api:app",
        "--host",
        host,
        "--port",
        str(port),
        "--workers",
        str(workers),
        "--proxy-headers",
        "--forwarded-allow-ips=*",
    ]

    print(f"[start.py] Launching canonical API: {' '.join(cmd)}")

    proc = subprocess.Popen(cmd, env=env)

    def _forward(signum, _frame):
        print(f"[start.py] Forwarding signal {signum} to uvicorn (pid={proc.pid})")
        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _forward)

    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
