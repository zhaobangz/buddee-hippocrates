import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
//
// FE-05 (April-21 re-audit):
// The `server.proxy` block forwards `/api/*` requests from the Vite dev
// server (port 5173) to the canonical backend at http://localhost:8001.
// Without this, local development required either a wildcard CORS allow-list
// (explicitly rejected by backend/api.py's `_cors_origins()`) or a separate
// reverse proxy. Routing through Vite avoids both.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
