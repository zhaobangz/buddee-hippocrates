#!/usr/bin/env python3
"""
Provision a new Buddee tenant.

Usage:
  python scripts/provision_tenant.py --slug acme-billing --name "Acme Medical Billing" \
      --physician-count 12 --scopes clinician,ingest,admin

Outputs the raw API key ONCE to stdout. It is never stored in plaintext.
"""
import argparse
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Make `python scripts/provision_tenant.py` runnable from anywhere: the script
# lives in scripts/, so put the repo root on sys.path before importing the app
# packages (mirrors tests/conftest.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Inline minimal DB setup to avoid importing the full FastAPI app
from core.database import SessionLocal
from core.models import Tenant, TenantApiKey
from backend.auth import hash_api_key, api_key_lookup_hash

def provision(slug: str, name: str, physician_count: int, scopes: list[str]) -> str:
    db = SessionLocal()
    try:
        existing = db.query(Tenant).filter_by(name=name).first()
        if existing:
            print(f"ERROR: Tenant with name '{name}' already exists (id={existing.id})", file=sys.stderr)
            sys.exit(1)

        tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            created_at=datetime.now(timezone.utc),
        )
        db.add(tenant)
        db.flush()

        raw_key = f"buddi_{secrets.token_urlsafe(32)}"
        api_key_row = TenantApiKey(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            key_hash_sha256=api_key_lookup_hash(raw_key),
            hashed_key=hash_api_key(raw_key),
            scopes=scopes,
            created_at=datetime.now(timezone.utc),
        )
        db.add(api_key_row)
        db.commit()

        print("Tenant provisioned:")
        print(f"  id:              {tenant.id}")
        print(f"  name:            {tenant.name}")
        print(f"  physician_count: {physician_count}")
        print(f"  scopes:          {scopes}")
        print("")
        print("API Key (copy now — never shown again):")
        print(f"  {raw_key}")
        print("")
        print("Next step: set baa_confirmed=true after BAA is signed:")
        print(f"  UPDATE tenants SET baa_confirmed=true, baa_confirmed_at=now() WHERE id='{tenant.id}';")
        return raw_key
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--physician-count", type=int, default=1)
    parser.add_argument("--scopes", default="clinician,ingest", help="Comma-separated scopes")
    args = parser.parse_args()
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    provision(args.slug, args.name, args.physician_count, scopes)
