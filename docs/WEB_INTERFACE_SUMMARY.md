# Web Interface Summary (Current)

Buddi includes an optional React/Vite frontend in `frontend/` that is useful for local development, demos, and UI experiments.

## Current position

- **Canonical product surface:** authenticated backend API (`backend.api:app`, port `8001`)
- **Frontend status:** available and runnable, but not the source of truth for production integrations
- **Known gap:** some frontend store calls still target legacy endpoints and need route alignment with backend v4.1

## What the frontend currently offers

- Multi-page UI shell (`Dashboard`, `Chat`, `Shadow`, `Audit`)
- Route-level error boundaries for resilience
- Vite dev proxy support for `/api` requests
- Environment-driven API base URL (`VITE_API_BASE`)

## Recommendation

Treat the frontend as a companion surface while API contracts are stabilized. For production integrations, rely on the backend route map documented in:

- `README.md`
- `docs/FRONTEND_BACKEND_CONNECTION.md`
