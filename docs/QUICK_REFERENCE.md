# Buddi Quick Reference (Current v4.1)

## 1) Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Minimum required `.env` values:

- `SECRET_KEY`
- `BUDDI_STORAGE_KEY`
- `DATABASE_URL`
- `API_KEY`

## 2) Database + run

```bash
alembic upgrade head
python start.py
```

Docs: `http://localhost:8001/docs`

Dev mode (backend reload + optional frontend):

```bash
python start_dev.py
```

## 3) Auth header (required)

```bash
Authorization: Bearer <API_KEY>
```

or

```bash
X-API-Key: <API_KEY>
```

## 4) API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | API + DB status |
| `/ingest/fhir` | POST | Ingest validated FHIR bundle |
| `/encounter/{encounter_id}/process` | POST | Encounter process marker |
| `/billing/suggest` | GET | Read HCC suggestions |
| `/prior-auth/generate` | POST | Generate prior-auth draft |
| `/audit/query` | GET | Read recent audit events |

## 5) Smoke checks

```bash
pytest -q
python scripts/verify_system.py
BUDDI_TEST_MODE=1 python scripts/verify_reaudit_fixes.py
```

## 6) Common troubleshooting

- **401 on every endpoint**: missing/invalid `API_KEY` header.
- **Startup fails with config error**: insecure or empty `SECRET_KEY` / `BUDDI_STORAGE_KEY` / `DATABASE_URL`.
- **DB errors**: verify Postgres is reachable and `alembic upgrade head` succeeded.

