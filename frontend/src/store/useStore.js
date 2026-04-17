import { create } from 'zustand';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

const useStore = create((set, get) => ({
  // Patient Context
  currentPatient: {
    id: 'PT-9012',
    name: 'Marcus Holloway',
    conditions: ['Type 2 Diabetes', 'Hypertension'],
    medications: ['Metformin 1000mg', 'Lisinopril 10mg'],
    labs: { a1c: 7.4, bp: '138/88' }
  },
  
  // Chat State
  messages: [
    {
      id: 1,
      role: 'assistant',
      content: 'Clinical System Online. Ready for patient context or queries.',
      timestamp: new Date().toISOString()
    }
  ],

  // Actions
  addMessage: (msg) => set((state) => ({ 
    messages: [...state.messages, { ...msg, id: Date.now(), timestamp: new Date().toISOString() }] 
  })),

  sendMessage: async (text) => {
    const { addMessage, currentPatient } = get();
    addMessage({ role: 'user', content: text });
    
    try {
      const resp = await axios.post(`${API_BASE}/chat/chat`, { 
        message: text,
        patient_id: currentPatient.id
      });
      addMessage({ 
        role: 'assistant', 
        content: resp.data.response,
        citations: resp.data.citations,
        intent: resp.data.intent_detected
      });
    } catch (err) {
      addMessage({ 
        role: 'assistant', 
        content: "Error: Could not connect to Buddi Backend. Ensure the FastAPI server is running on port 8000.",
        isError: true
      });
    }
  },

  fetchPatientProfile: async (patientId) => {
    const id = patientId || get().currentPatient.id;
    try {
      const resp = await axios.get(`${API_BASE}/patient/${id}`);
      set({ currentPatient: resp.data });
    } catch (err) {
      console.error("Failed to fetch patient profile");
    }
  },

  // Audit Events
  auditEvents: [],
  fetchAuditLogs: async () => {
    try {
      const resp = await axios.get(`${API_BASE}/audit/`);
      set({ auditEvents: resp.data });
    } catch (err) {
      console.error("Failed to fetch audit logs");
    }
  }
}));

export default useStore;
