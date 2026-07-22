"""Database engine & session management (ARCH-03, SEC-04 hardening).

Pool is explicitly sized so that a burst of concurrent FastAPI requests cannot
exhaust the PostgreSQL connection limit. ``pool_pre_ping`` guarantees stale
connections (e.g. after a DB restart) are reaped transparently.

SEC-04 (April-21 re-audit): the ``postgres:postgres`` fallback credential is
refused at import time unless ``BUDDI_TEST_MODE=1`` is set. Production start
therefore cannot silently bind to a world-readable Postgres instance.
"""

import os

_DEFAULT_DEV_URL = "postgresql://postgres:postgres@localhost:5432/buddi"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    if os.getenv("BUDDI_TEST_MODE") == "1":
        DATABASE_URL = _DEFAULT_DEV_URL
    else:
        raise RuntimeError("DATABASE_URL is not configured. Set it in your .env file.")

# E402 is intentional here — the runtime DATABASE_URL validation above must
# fail loudly *before* SQLAlchemy is imported so misconfigured production
# starts surface as a clear error rather than a deferred ImportError.
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SEC-04: refuse to start with the dev-default credential outside of an
# explicit test-mode context. Alembic migrations set DATABASE_URL explicitly,
# CI sets BUDDI_TEST_MODE=1, and local dev uses a non-default password — so
# the only caller this blocks is an accidental production boot.
if os.getenv("BUDDI_TEST_MODE") != "1" and "postgres:postgres@" in DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is using the insecure `postgres:postgres` default. "
        "Set DATABASE_URL to a dedicated Postgres credential before starting "
        "the service (see .env.example and core/config.py::SEC-04)."
    )


engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
