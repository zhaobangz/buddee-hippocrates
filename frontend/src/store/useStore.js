import { create } from 'zustand';
import axios from 'axios';

/**
 * API base URL.
 *
 * Track 1 / Step 1 (FE-01, CFG-01): the canonical backend is
 * `backend.api:app` on port 8001. The base is injected at build time via
 * Vite's `VITE_API_BASE` (or `VITE_API_BASE_URL`) env var so dev, staging,
 * and production can each target their own deployment without code changes.
 *
 * Safe default: localhost:8001/api (dev). In production (Vercel), set
 * `VITE_API_BASE` to your deployed backend URL at build time.
 *
 * Example `frontend/.env.local`:
 *   VITE_API_BASE=http://localhost:8001/api
 */
const API_BASE =
  (import.meta.env && (import.meta.env.VITE_API_BASE || import.meta.env.VITE_API_BASE_URL)) ||
  'http://localhost:8001/api';
const API_KEY_ENV = import.meta.env && import.meta.env.VITE_API_KEY;

// In-memory only — never persisted to localStorage. The user is prompted on
// first 401 if VITE_API_KEY was not baked into the build.
let runtimeApiKey = API_KEY_ENV || null;
const apiKeyListeners = new Set();
function setRuntimeApiKey(key) {
  runtimeApiKey = key || null;
  apiKeyListeners.forEach((cb) => cb(runtimeApiKey));
}
export function getRuntimeApiKey() {
  return runtimeApiKey;
}
export function subscribeApiKey(cb) {
  apiKeyListeners.add(cb);
  return () => apiKeyListeners.delete(cb);
}

// ---------------------------------------------------------------------------
// Portal session (human lane) — email+password+hCaptcha login issues a
// short-lived access JWT plus a rotating refresh token. Both live in module
// memory ONLY (same posture as the API key: nothing in localStorage), so a
// browser refresh simply means signing in again.
// ---------------------------------------------------------------------------
let runtimeSession = null;
const sessionListeners = new Set();
function setRuntimeSession(session) {
  runtimeSession = session || null;
  sessionListeners.forEach((cb) => cb(runtimeSession));
}
export function getRuntimeSession() {
  return runtimeSession;
}
export function subscribeSession(cb) {
  sessionListeners.add(cb);
  return () => sessionListeners.delete(cb);
}
function applySessionPayload(data) {
  if (!data || !data.access_token) {
    setRuntimeSession(null);
    return null;
  }
  const session = {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    user: data.user || null,
    expiresIn: data.expires_in,
  };
  setRuntimeSession(session);
  return session;
}

// Dedicated axios instance so auth headers (Track 1 / Step 3) and request IDs
// (Track 2 Step 22) can be attached in a single place later.
const api = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
});

// Build-out B4.3: human-facing labels for the async shadow-audit job stream.
// The frontend never shows raw job internals — only these three states.
const SHADOW_PROGRESS_LABELS = {
  pending: 'Retrieving guidelines...',
  processing: 'Running analysis...',
  completed: 'Complete.',
};

// Consume the SSE job-progress stream (GET /jobs/{id}/stream) via fetch rather
// than EventSource, so the in-memory X-API-Key header travels with the request
// (the HIPAA posture keeps the key out of URLs/localStorage). Falls back to
// polling GET /jobs/{id} if the stream is unavailable. Resolves to the final
// ShadowModeResponse payload.
async function streamShadowJob(jobId, onProgress) {
  try {
    const key = getRuntimeApiKey();
    const resp = await fetch(`${API_BASE}/jobs/${jobId}/stream`, {
      headers: key ? { 'X-API-Key': key } : {},
    });
    if (!resp.ok || !resp.body) throw new Error(`stream ${resp.status}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const dataLine = frame.split('\n').find((l) => l.startsWith('data:'));
        if (!dataLine) continue;
        let evt;
        try {
          evt = JSON.parse(dataLine.slice(5).trim());
        } catch {
          continue;
        }
        if (evt.status && SHADOW_PROGRESS_LABELS[evt.status]) {
          onProgress(SHADOW_PROGRESS_LABELS[evt.status]);
        }
        if (evt.status === 'completed') return evt.result;
        if (evt.status === 'failed') throw new Error(evt.error || 'Shadow audit failed');
      }
    }
  } catch {
    // Stream unavailable / interrupted — fall back to polling.
  }
  return pollShadowJob(jobId, onProgress);
}

// I-8/QW-8: exponential backoff (1s → 2s → 4s → 5s cap) inside a 150s
// budget instead of a fixed 1s × 60 loop — fewer HTTP calls per job, and a
// deadline that tolerates real LLM latency instead of a hardcoded count.
async function pollShadowJob(jobId, onProgress) {
  const deadline = Date.now() + 150_000;
  let delay = 1_000;
  while (Date.now() < deadline) {
    const resp = await api.get(`/jobs/${jobId}`);
    const { status, result, error } = resp.data || {};
    if (status && SHADOW_PROGRESS_LABELS[status]) onProgress(SHADOW_PROGRESS_LABELS[status]);
    if (status === 'completed') return result;
    if (status === 'failed') throw new Error(error || 'Shadow audit failed');
    await new Promise((resolve) => setTimeout(resolve, delay));
    delay = Math.min(delay * 2, 5_000);
  }
  throw new Error('Shadow audit timed out');
}

api.interceptors.request.use((config) => {
  config.headers = config.headers || {};
  // Human lane wins when a portal session exists; machine lane (API key)
  // covers integrations and the "use an API key instead" path.
  if (runtimeSession?.accessToken) {
    config.headers['Authorization'] = `Bearer ${runtimeSession.accessToken}`;
  } else if (runtimeApiKey) {
    config.headers['X-API-Key'] = runtimeApiKey;
  }
  return config;
});

// Attempt one silent token refresh on 401 (non-auth endpoints), then retry
// the original request with the new access token. Uses a bare axios call so
// the refresh itself cannot re-enter this interceptor.
let refreshInFlight = null;
async function trySilentRefresh() {
  if (!runtimeSession?.refreshToken) return false;
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post(`${API_BASE}/auth/refresh`, { refresh_token: runtimeSession.refreshToken })
      .then((resp) => applySessionPayload(resp.data))
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  const session = await refreshInFlight;
  return Boolean(session);
}

// On 401, surface a flag to the UI so it can prompt for a key once.
api.interceptors.response.use(
  (resp) => resp,
  async (err) => {
    const status = err?.response?.status;
    const url = err?.config?.url || '';
    const isAuthEndpoint = url.includes('/auth/');
    if (status === 401 && !isAuthEndpoint && !err.config.__retriedAfterRefresh) {
      const refreshed = await trySilentRefresh();
      if (refreshed) {
        err.config.__retriedAfterRefresh = true;
        return api.request(err.config);
      }
    }
    if (status === 401) {
      apiKeyListeners.forEach((cb) => cb(null, { unauthorized: true }));
      if (!isAuthEndpoint) {
        setRuntimeSession(null);
      }
    }
    return Promise.reject(err);
  },
);


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
  shadowProgress: null,
  // Build-out B6: tenant-scoping indicator, SLO observability, demo-mode flag.
  tenantId: null,
  sloMetrics: null,
  demoMode: false,

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
      // B6.4: a network-level failure means there is no live backend — flag
      // demo mode so the Chat page shows the "Demo mode (no live backend)" banner.
      if (!err?.response) set({ demoMode: true });
      addMessage({
        role: 'assistant',
        content: `Error: Could not reach Buddee Health backend at ${API_BASE} (${reason}). Ensure the canonical API (backend.api:app) is running.`,
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
      // B6.4: the demo endpoint tags canned data via X-Response-Source.
      if (resp.headers?.['x-response-source'] === 'canned') set({ demoMode: true });
      set({ currentPatient: resp.data });
      return resp.data;
    } catch (err) {
      console.error('Failed to load demo patient', err);
      return get().currentPatient;
    }
  },

  // B6.2: fetch the tenant context (the API never exposes the key, only the
  // tenant UUID) for the dashboard tenant-scoping indicator.
  fetchTenantContext: async () => {
    try {
      const resp = await api.get('/health');
      if (resp.data?.tenant_id) set({ tenantId: resp.data.tenant_id });
    } catch (err) {
      console.error('Failed to fetch tenant context', err);
    }
  },

  // PROMPT_07 / C2: fetch the PHI-safe SLO snapshot for the SLO panel. Tracks
  // an error flag so the panel can render "SLO data unavailable" gracefully.
  sloError: false,
  fetchSloMetrics: async () => {
    try {
      const resp = await api.get('/metrics/slo');
      if (resp.headers?.['x-response-source'] === 'canned') set({ demoMode: true });
      set({ sloMetrics: resp.data, sloError: false });
    } catch (err) {
      console.error('Failed to fetch SLO metrics', err);
      set({ sloMetrics: null, sloError: true });
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

    set({
      isShadowLoading: true,
      shadowError: null,
      shadowProgress: SHADOW_PROGRESS_LABELS.pending,
    });

    const finish = (result) => {
      set({ shadowResult: result, isShadowLoading: false, shadowProgress: null });
      get().fetchAuditLogs();
      get().fetchDashboardMetrics();
      return result;
    };

    try {
      // B3: async by default — POST returns 202 + job_id, or 200 with a cached
      // result. (The legacy synchronous body is still handled for safety.)
      const resp = await api.post('/shadow/audit', payload);
      const data = resp.data || {};
      if (data.result) return finish(data.result); // cached completed job
      if (!data.job_id) return finish(data); // legacy synchronous shape
      const result = await streamShadowJob(data.job_id, (label) =>
        set({ shadowProgress: label }),
      );
      return finish(result);
    } catch (err) {
      console.error('Shadow audit failed', err);
      const message = err?.response?.data?.detail || err?.message || 'Shadow audit failed';
      set({ shadowError: message, isShadowLoading: false, shadowProgress: null });
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

  // Prior-auth draft (deliverable 4.5)
  priorAuthDraft: null,
  isPriorAuthLoading: false,
  priorAuthError: null,
  generatePriorAuth: async ({ procedureCode, payer, encounterId, clinicalContext, demo = false } = {}) => {
    set({ isPriorAuthLoading: true, priorAuthError: null });
    try {
      const resp = await api.post(
        '/prior-auth/generate',
        {
          procedure_code: procedureCode || 'CPT-99213',
          payer: payer || 'Medicare',
          encounter_id: encounterId,
          clinical_context: clinicalContext,
          demo,
        },
        { timeout: 60_000 },
      );
      set({ priorAuthDraft: resp.data, isPriorAuthLoading: false });
      get().fetchAuditLogs();
      return resp.data;
    } catch (err) {
      const message = err?.response?.data?.detail || err?.message || 'Prior-auth generation failed';
      set({ priorAuthError: message, isPriorAuthLoading: false });
      throw err;
    }
  },

  // Auth ergonomics: prompt-once for an API key when VITE_API_KEY isn't baked in.
  apiKey: runtimeApiKey,
  setApiKey: (key) => {
    setRuntimeApiKey(key);
    set({ apiKey: key });
  },

  // --- Portal session (human lane: email + password + hCaptcha) ---
  // Session tokens live in module memory only; the store mirrors them for
  // reactive UI. `preferApiKey` lets a user explicitly choose the machine
  // lane from the login page (kept out of the guard's way).
  session: null,
  user: null,
  preferApiKey: false,
  setPreferApiKey: (value) => set({ preferApiKey: Boolean(value) }),
  login: async ({ email, password, captchaToken }) => {
    const resp = await api.post('/auth/login', {
      email,
      password,
      captcha_token: captchaToken || null,
    });
    const session = applySessionPayload(resp.data);
    set({ session, user: session?.user || null, preferApiKey: false });
    return session;
  },
  signup: async ({ inviteToken, email, password, fullName, captchaToken }) => {
    const resp = await api.post('/auth/signup', {
      invite_token: inviteToken,
      email,
      password,
      full_name: fullName || null,
      captcha_token: captchaToken || null,
    });
    const session = applySessionPayload(resp.data);
    set({ session, user: session?.user || null, preferApiKey: false });
    return session;
  },
  logout: async () => {
    const refreshToken = runtimeSession?.refreshToken;
    try {
      if (refreshToken) {
        await api.post('/auth/logout', { refresh_token: refreshToken });
      }
    } catch (err) {
      // Logout must succeed locally even if the revoke call fails.
      console.warn('Refresh-token revoke failed (signing out locally anyway)', err);
    } finally {
      applySessionPayload(null);
      set({ session: null, user: null });
    }
  },

  // Demo-mode bootstrap: load synthetic patient + run one shadow audit.
  // Used by `?demo=true` and the "Try Sample Patient" CTA. Idempotent.
  runDemoBootstrap: async () => {
    try {
      const patient = await get().loadDemoPatient();
      await get().runShadowAudit({ patientId: patient?.id || 'PT-9012', demo: true });
      await get().fetchAuditLogs();
    } catch (err) {
      console.error('Demo bootstrap failed', err);
    }
  },
}));

// Keep zustand state mirrored when the session changes outside store actions
// (silent refresh success, or the 401 interceptor clearing a dead session).
subscribeSession((session) => {
  useStore.setState({ session, user: session?.user || null });
});

export default useStore;
export { API_BASE, api };
