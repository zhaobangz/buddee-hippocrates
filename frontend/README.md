# Buddi Frontend (Vite + React)

This directory contains Buddi's optional web UI for local development/demo flows.

## Current status

- The backend (`backend.api:app`) is the canonical production surface.
- This frontend is actively runnable for dev, but not all UI actions are fully aligned with the current backend route set.
- API base URL is configured via `VITE_API_BASE` (see `.env.example`).

## Prerequisites

- Node.js 20+
- npm 10+
- Backend running on `http://localhost:8001` (or another URL you set in `VITE_API_BASE`)

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local
```

Default local env:

```env
VITE_API_BASE=http://localhost:8001/api
```

## Run

```bash
# from frontend/
npm run dev
```

Vite dev server: `http://localhost:5173`

You can also start both backend + frontend from repo root:

```bash
python start_dev.py
```

## Build

```bash
npm run build
npm run preview
```

## Integration notes (important)

`src/store/useStore.js` currently includes some legacy calls (for example `/chat/chat`, `/patient/:id`, `/audit/`) that do not map 1:1 to the backend v4.1 routes. The backend routes currently available are documented in the root `README.md` and `docs/FRONTEND_BACKEND_CONNECTION.md`.

When wiring production UI behavior, use the canonical backend endpoints (e.g. `/api/health`, `/ingest/fhir`, `/audit/query`, `/prior-auth/generate`).
