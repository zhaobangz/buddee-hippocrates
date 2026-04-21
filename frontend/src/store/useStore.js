import { create } from 'zustand';
import axios from 'axios';

/**
 * API base URL.
 *
 * Track 1 / Step 1 (FE-01, CFG-01): the canonical backend is
 * `backend.api:app` on port 8001. The base is now injected at build time via
 * Vite's `VITE_API_BASE` env var so dev, staging, and production can each
 * target their own deployment without code changes.
 *
 * Example `frontend/.env.local`:
 *   VITE_API_BASE=http://localhost:8001/api
 */
const API_BASE =
  (import.meta.env && import.meta.env.VITE_API_BASE) ||
  'http://localhost:8001/api';

// Dedicated axios instance so auth headers (Track 1 / Step 3) and request IDs
// (Track 2 Step 22) can be attached in a single place later.
const api = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
});

const useStore = create((set, get) => ({
  // Patient Context (placeholder until Track 2 Step 15 wires real data)
  currentPatient: {
    id: 'PT-9012',
    name: 'Marcus Holloway',
    conditions: ['Type 2 Diabetes', 'Hypertension'],
    medications: ['Metformin 1000mg', 'Lisinopril 10mg'],
    labs: { a1c: 7.4, bp: '138/88' },
  },

  // Chat State
  messages: [
    {
      id: 1,
      role: 'assistant',
      content: 'Clinical System Online. Ready for patient context or queries.',
      timestamp: new Date().toISOString(),
    },
  ],

  // Actions
  addMessage: (msg) =>
    set((state) => ({
      messages: [
        ...state.messages,
        { ...msg, id: Date.now(), timestamp: new Date().toISOString() },
      ],
    })),

  sendMessage: async (text) => {
    const { addMessage, currentPatient } = get();
    addMessage({ role: 'user', content: text });

    try {
      const resp = await api.post('/chat/chat', {
        message: text,
        patient_id: currentPatient.id,
      });
      addMessage({
        role: 'assistant',
        content: resp.data.response,
        citations: resp.data.citations,
        intent: resp.data.intent_detected,
      });
    } catch (err) {
      console.error('sendMessage failed', err);
      const reason = err?.response?.status
        ? `HTTP ${err.response.status}`
        : err?.message || 'network error';
      addMessage({
        role: 'assistant',
        content: `Error: Could not reach Buddi backend at ${API_BASE} (${reason}). Ensure the canonical API (backend.api:app) is running.`,
        isError: true,
      });
    }
  },

  fetchPatientProfile: async (patientId) => {
    const id = patientId || get().currentPatient.id;
    try {
      const resp = await api.get(`/patient/${id}`);
      set({ currentPatient: resp.data });
    } catch (err) {
      console.error('Failed to fetch patient profile', err);
    }
  },

  // Audit Events
  auditEvents: [],
  fetchAuditLogs: async () => {
    try {
      const resp = await api.get('/audit/');
      set({ auditEvents: resp.data });
    } catch (err) {
      console.error('Failed to fetch audit logs', err);
    }
  },
}));

export default useStore;
export { API_BASE, api };
