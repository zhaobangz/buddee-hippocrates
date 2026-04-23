# Frontend ↔ Backend Connection Guide (Current v4.1)

This document reflects the **current** integration contract between Buddi's optional React frontend and the canonical FastAPI backend.

## Runtime topology

- Backend: `backend.api:app` on `http://localhost:8001`
- Frontend (optional): Vite on `http://localhost:5173`
- Frontend API base env: `VITE_API_BASE` (default: `http://localhost:8001/api`)

> Note: Backend routes are not uniformly prefixed with `/api` today. `GET /api/health` uses `/api`, while routes like `/ingest/fhir` and `/audit/query` do not.

## Authentication requirements

All backend endpoints require auth via either:

- `X-API-Key: <API_KEY>`
- `Authorization: Bearer <API_KEY or SECRET_KEY>`

Frontend/API clients should attach an auth header on every request.

## Current backend route map

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Liveness + DB status |
| `/ingest/fhir` | POST | FHIR bundle ingest + shadow-mode processing |
| `/encounter/{encounter_id}/process` | POST | Encounter processing marker |
| `/billing/suggest` | GET | Retrieve HCC suggestions |
| `/prior-auth/generate` | POST | Create prior-auth draft |
| `/audit/query` | GET | Read recent audit events |

## Frontend alignment status

`frontend/src/store/useStore.js` still contains legacy paths:

- `POST /chat/chat`
- `GET /patient/:id`
- `GET /audit/`

Those do not match backend v4.1 routes. Treat them as transitional UI wiring, not production API contract.

## Recommended local dev setup

1. Start backend: `python start_dev.py` (or `python start.py`)
2. Ensure frontend `.env.local` sets `VITE_API_BASE`
3. Add auth headers to axios instance in `useStore.js`
4. Point frontend calls to canonical endpoints above

## Minimal connectivity test

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8001/api/health
```

If this succeeds, the backend is reachable and accepting authenticated traffic.
