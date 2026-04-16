import { create } from 'zustand';
import axios from 'axios';

const API_BASE = 'http://localhost:8001/api';

const useStore = create((set, get) => ({
  // Patient Context
  currentPatient: {
    id: 'P-8829',
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
      content: 'System Online. Awaiting clinical query.',
      timestamp: new Date().toISOString()
    }
  ],

  // Actions
  addMessage: (msg) => set((state) => ({ 
    messages: [...state.messages, { ...msg, id: Date.now(), timestamp: new Date().toISOString() }] 
  })),

  sendMessage: async (text) => {
    const { addMessage } = get();
    addMessage({ role: 'user', content: text });
    
    try {
      const resp = await axios.post(`${API_BASE}/chat`, { message: text });
      addMessage({ 
        role: 'assistant', 
        content: resp.data.response,
        status: resp.data.status
      });
    } catch (err) {
      addMessage({ 
        role: 'assistant', 
        content: "Error: Could not connect to clinical backend. Ensure 'python start.py' is running on port 8001.",
        isError: true
      });
    }
  },

  fetchPatientProfile: async () => {
    try {
      const resp = await axios.get(`${API_BASE}/patient`);
      if (resp.data.status === 'success') {
        set({ currentPatient: resp.data.context });
      }
    } catch (err) {
      console.error("Failed to fetch patient profile");
    }
  },

  // Audit Events
  auditEvents: [],
  fetchAuditLogs: async () => {
    try {
      const resp = await axios.get(`${API_BASE}/audit`);
      set({ auditEvents: resp.data.events });
    } catch (err) {
      console.error("Failed to fetch audit logs");
    }
  }
}));

export default useStore;
