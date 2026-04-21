"""Database engine & session management (ARCH-03 hardening).

Pool is explicitly sized so that a burst of concurrent FastAPI requests cannot
exhaust the PostgreSQL connection limit. ``pool_pre_ping`` guarantees stale
connections (e.g. after a DB restart) are reaped transparently.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/buddi",
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
