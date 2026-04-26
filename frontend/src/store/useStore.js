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
const API_KEY = import.meta.env && import.meta.env.VITE_API_KEY;

// Dedicated axios instance so auth headers (Track 1 / Step 3) and request IDs
// (Track 2 Step 22) can be attached in a single place later.
const api = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
});

api.interceptors.request.use((config) => {
  if (API_KEY) {
    config.headers = config.headers || {};
    config.headers['X-API-Key'] = API_KEY;
  }
  return config;
});

const defaultShadowResult = {
  demo: true,
  patient_id: 'PT-9012',
  recovered_revenue: 0,
  identified_codes: [],
  citations: [],
  summary: 'Paste a note or try the synthetic patient to run a shadow-mode revenue audit.',
};

const defaultMetrics = {
  demo: true,
  total_recovered_revenue: 0,
  missed_codes_found: 0,
  average_value_per_encounter: 0,
  accepted_rate: 0,
  rejected_rate: 0,
  top_categories: [],
  audit_integrity_status: 'not_verified',
};

const useStore = create((set, get) => ({
  // Patient Context (placeholder until Track 2 Step 15 wires real data)
  currentPatient: {
    id: 'PT-9012',
    name: 'Marcus Holloway',
    demo: true,
    conditions: ['Type 2 Diabetes', 'CKD stage 3a', 'Hypertension'],
    medications: ['Metformin 1000mg', 'Lisinopril 10mg', 'Atorvastatin 20mg'],
    labs: { a1c: 7.4, bp: '138/88', egfr: 51, uacr: '42 mg/g' },
    billed_codes: ['E11.9', 'I10'],
    clinical_note:
      '67-year-old male with type 2 diabetes mellitus complicated by chronic kidney disease stage 3a. eGFR 51 and urine albumin/creatinine ratio 42 mg/g. Hypertension treated with lisinopril. Assessment notes diabetic CKD and hypertensive CKD; continue renal-protective therapy and monitor BMP.',
  },
  dashboardMetrics: defaultMetrics,
  shadowResult: defaultShadowResult,
  isShadowLoading: false,
  shadowError: null,

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
      if (resp.data.shadow_result) {
        set({ shadowResult: resp.data.shadow_result });
        get().fetchDashboardMetrics();
      }
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

  loadDemoPatient: async () => {
    try {
      const resp = await api.get('/demo/sample-patient');
      set({ currentPatient: resp.data });
      return resp.data;
    } catch (err) {
      console.error('Failed to load demo patient', err);
      return get().currentPatient;
    }
  },

  runShadowAudit: async ({ note, billedCodes, patientId, demo = false } = {}) => {
    const { currentPatient } = get();
    const payload = {
      note: note || currentPatient.clinical_note || '',
      billed_codes: billedCodes || currentPatient.billed_codes || [],
      patient_id: patientId || currentPatient.id,
      demo,
    };

    set({ isShadowLoading: true, shadowError: null });
    try {
      const resp = await api.post('/shadow/audit', payload);
      set({ shadowResult: resp.data, isShadowLoading: false });
      get().fetchAuditLogs();
      get().fetchDashboardMetrics();
      return resp.data;
    } catch (err) {
      console.error('Shadow audit failed', err);
      const message = err?.response?.data?.detail || err?.message || 'Shadow audit failed';
      set({ shadowError: message, isShadowLoading: false });
      throw err;
    }
  },

  fetchDashboardMetrics: async () => {
    try {
      const resp = await api.get('/dashboard/metrics');
      set({ dashboardMetrics: resp.data });
    } catch (err) {
      console.error('Failed to fetch dashboard metrics', err);
    }
  },

  // Audit Events
  auditEvents: [],
  auditVerification: null,
  fetchAuditLogs: async () => {
    try {
      const resp = await api.get('/audit/query');
      set({
        auditEvents: resp.data.events || [],
        auditVerification: resp.data.verification || null,
      });
    } catch (err) {
      console.error('Failed to fetch audit logs', err);
    }
  },

  verifyAuditTrail: async () => {
    try {
      const resp = await api.get('/audit/verify');
      set({ auditVerification: resp.data });
      return resp.data;
    } catch (err) {
      console.error('Failed to verify audit trail', err);
      return null;
    }
  },
}));

export default useStore;
export { API_BASE, api };
