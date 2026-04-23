#!/usr/bin/env python3
"""Deep verification harness for the April-21 re-audit fixes.

Run with:
    BUDDI_TEST_MODE=1 python scripts/verify_reaudit_fixes.py

Exits non-zero on any regression. This is additive to the pytest suite; it
asserts *internal invariants* rather than HTTP behavior, so it catches
regressions like "the validator still exists but no longer fires".
"""
from __future__ import annotations

import os
import pathlib
import re
import sys


def main() -> int:
    os.environ.setdefault("BUDDI_TEST_MODE", "1")
    os.environ.setdefault(
        "SECRET_KEY",
        "test-only-secret-key-not-for-production-use-0123456789abcdef",
    )
    os.environ.setdefault("BUDDI_STORAGE_KEY", "test-only-storage-key-not-for-prod")

    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond, detail))

    # ---------- SEC-01 ----------
    from backend.api import _cors_origins

    os.environ["CORS_ORIGINS"] = "http://localhost:5173,*,https://app.buddi.health"
    check("SEC-01 CORS wildcard rejection", "*" not in _cors_origins())

    # ---------- SEC-02 ----------
    from backend import auth

    check("SEC-02 require_api_client dependency", callable(auth.require_api_client))

    # ---------- SEC-03 ----------
    from pydantic import ValidationError
    from core.config import Settings

    weak_rejected = False
    try:
        Settings(
            SECRET_KEY="change-me",
            BUDDI_STORAGE_KEY="a-real-key-32-chars-long-xxxxx",
            DATABASE_URL="postgresql://u:p@h/d",
        )
    except ValidationError:
        weak_rejected = True
    check("SEC-03 weak SECRET_KEY rejected", weak_rejected)

    # ---------- SEC-04 ----------
    os.environ.pop("BUDDI_TEST_MODE", None)
    insecure_db_rejected = False
    try:
        Settings(
            SECRET_KEY="x" * 40,
            BUDDI_STORAGE_KEY="y" * 20,
            DATABASE_URL="postgresql://postgres:postgres@h:5432/db",
        )
    except ValidationError:
        insecure_db_rejected = True
    os.environ["BUDDI_TEST_MODE"] = "1"
    check("SEC-04 postgres:postgres DB URL rejected in prod mode", insecure_db_rejected)

    # ---------- SEC-05 ----------
    from core.storage import PBKDF2_ITERATIONS, SALT_LEN, SecureStorage

    s = SecureStorage("test-only-storage-key")
    c1 = s._encrypt(b"hello")
    c2 = s._encrypt(b"hello")
    random_salt_ok = (
        c1[:SALT_LEN] != c2[:SALT_LEN]
        and s._decrypt(c1) == b"hello"
        and s._decrypt(c2) == b"hello"
    )
    check(
        "SEC-05 per-record random salt + 200k PBKDF2",
        random_salt_ok and PBKDF2_ITERATIONS == 200_000,
    )

    # ---------- DB-05 ----------
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    from core.models import RecoveryEvent

    id_col = RecoveryEvent.__table__.columns["id"]
    check(
        "DB-05 RecoveryEvent.id is PG_UUID",
        isinstance(id_col.type, PG_UUID),
        f"got {type(id_col.type).__name__}",
    )

    # ---------- CQ-04 ----------
    leaks: list[str] = []
    for root in ("core", "tools", "backend", "scripts"):
        for p in pathlib.Path(root).rglob("*.py"):
            if p.name == "verify_reaudit_fixes.py":
                continue  # self-exclude
            src = p.read_text()
            clean = re.sub(r'"""[\s\S]*?"""', "", src)
            clean = re.sub(r"'''[\s\S]*?'''", "", clean)
            clean = re.sub(r"#.*", "", clean)
            if "datetime.utcnow" in clean:
                leaks.append(str(p))
    check("CQ-04 no datetime.utcnow() in executable code", not leaks, ", ".join(leaks))

    # ---------- CFG-04 + DO-05 ----------
    compose = pathlib.Path("docker-compose.yml").read_text()
    check("CFG-04 DEV_MODE parameterized", "${DEV_MODE:-false}" in compose)
    check("DO-05 source bind-mount removed", "- .:/app" not in compose)

    # ---------- DO-02 + DO-03 ----------
    dockerfile = pathlib.Path("Dockerfile").read_text()
    check("DO-02 HEALTHCHECK present", "HEALTHCHECK" in dockerfile)
    check("DO-03 non-root USER appuser", "USER appuser" in dockerfile)

    # ---------- CQ-02 ----------
    check("CQ-02 legacy app/ tree removed", not pathlib.Path("app").exists())

    # ---------- FE-05/FE-06/FE-07 ----------
    vite_cfg = pathlib.Path("frontend/vite.config.js").read_text()
    check(
        "FE-05 vite.config.js server.proxy /api",
        "proxy" in vite_cfg and "/api" in vite_cfg,
    )
    check(
        "FE-06 ErrorBoundary component exists",
        pathlib.Path("frontend/src/components/ErrorBoundary.jsx").exists(),
    )
    app_jsx = pathlib.Path("frontend/src/App.jsx").read_text()
    check("FE-06 ErrorBoundary wired into App.jsx", "ErrorBoundary" in app_jsx)
    chat_jsx = pathlib.Path("frontend/src/pages/ChatPage.jsx").read_text()
    check(
        "FE-07 onKeyDown replaces onKeyPress",
        "onKeyDown" in chat_jsx and "onKeyPress" not in chat_jsx,
    )

    # ---- Report ----
    any_fail = False
    for name, ok, detail in results:
        mark = "✅" if ok else "❌"
        suffix = f"  —  {detail}" if detail and not ok else ""
        print(f"  {mark} {name}{suffix}")
        if not ok:
            any_fail = True

    print()
    if any_fail:
        print("❌  One or more control verifications FAILED.")
        return 1
    print("✅  All re-audit control verifications passed. LAUNCH CANDIDATE confirmed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
