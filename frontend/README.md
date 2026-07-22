# Buddi Frontend (Vite + React)

Operator UI for the Buddi RCM platform. React 19 + Vite 8 + Tailwind CSS 3.4 +
Zustand 5 + Chart.js.

## Current status

- Four pages: Dashboard (`/`), Review Queue (`/shadow`), Ask Buddee (`/chat`),
  Audit Trail (`/audit`)
- Demo mode via `?demo=true` loads synthetic patient PT-9012 (Marcus Holloway) and
  runs a deterministic shadow audit — no backend or LLM key required
- Dark/light theme persisted in localStorage
- API key in memory only (never localStorage/sessionStorage)
- SSE streaming for async job progress

## Prerequisites

- Node.js 20+
- npm 10+
- Backend running on `http://localhost:8001` (or another URL set in `VITE_API_BASE` / `VITE_API_BASE_URL`)

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local
```

Default local env:

```env
VITE_API_BASE=http://localhost:8001/api
VITE_API_KEY=your_api_key_here
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

## API contract

`src/store/useStore.js` is the Zustand store that manages all API calls via a shared
Axios instance. Backend routes are documented in the root `README.md`. Key endpoints
used by the frontend:

- `GET /api/health` — validate API key, get tenant info
- `GET /api/dashboard/metrics` — revenue recovery aggregates
- `POST /api/shadow/audit` — run shadow-mode HCC audit
- `GET /api/audit/query` — fetch audit trail entries
- `GET /api/audit/verify` — verify cryptographic chain integrity
- `POST /api/prior-auth/generate` — generate prior-auth draft
- `POST /api/chat/chat` — chat with agent
- `GET /api/jobs/{id}/stream` — SSE job progress

## Integration notes

- The frontend proxies `/api` to the backend in dev (`vite.config.js`)
- Production: set `VITE_API_BASE` (or `VITE_API_BASE_URL`) to the deployed backend URL
- Demo mode (`?demo=true`) uses deterministic canned responses — no backend required
- All async operations have loading, error, and empty states
- Error boundaries wrap each route for graceful degradation
