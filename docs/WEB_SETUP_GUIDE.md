# Web Setup Guide (Frontend Local Dev)

This guide covers running Buddi's optional React/Vite frontend against the current backend API.

## 1) Backend first

Start backend from repo root:

```bash
python3 start_dev.py
```

or production-parity launcher:

```bash
python3 start.py
```

Backend target: `http://localhost:8001`

## 2) Frontend env

From `frontend/`:

```bash
cp .env.example .env.local
```

Default value:

```env
VITE_API_BASE=http://localhost:8001/api
```

## 3) Install and run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

## 4) Backend auth reminder

Backend routes require auth. If you wire live calls from UI components, ensure your axios/fetch layer sends either:

- `Authorization: Bearer <API_KEY>`
- `X-API-Key: <API_KEY>`

## 5) Known integration mismatch

`frontend/src/store/useStore.js` still references some legacy endpoints (`/chat/chat`, `/patient/:id`, `/audit/`). Update those calls to backend v4.1 routes when doing production-facing frontend work.
