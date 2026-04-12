/**
 * Buddi Clinical Agent — Web UI Frontend Logic
 * Healthcare Workflow Intelligence
 */

// Configuration
// If the frontend is served from a server, try to guess the API URL
const DEFAULT_API_PORT = 8000;
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? `${window.location.protocol}//${window.location.hostname}:${DEFAULT_API_PORT}/api`
    : '/api'; // Fallback for production/relative paths

const RECONNECT_INTERVAL = 5000;

// State
let agentStatus = { connected: false, lastCheckTime: null };

// DOM Elements
const messagesContainer = document.getElementById('messagesContainer');
const userInput = document.getElementById('userInput');
const chatForm = document.getElementById('chatForm');
const sendButton = document.getElementById('sendButton');
const resetButton = document.getElementById('resetButton');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorToast = document.getElementById('errorToast');
const toastMessage = document.getElementById('toastMessage');
const clearPatientBtn = document.getElementById('clearPatientBtn');
const patientModeToggle = document.getElementById('patientModeToggle');
const imageUpload = document.getElementById('imageUpload');
const compareShadowBtn = document.getElementById('compareShadowBtn');
const expertActionInput = document.getElementById('expertActionInput');
const shadowComparisonOutput = document.getElementById('shadowComparisonOutput');
const dashboardView = document.getElementById('dashboardView');
const shadowView = document.getElementById('shadowView');
const chatContainer = document.getElementById('chatContainer');
const micBtn = document.getElementById('micBtn');
const micRings = document.getElementById('micRings');
const perceptionStatus = document.getElementById('perceptionStatus');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing Buddi Clinical Agent Web UI...');

    chatForm.addEventListener('submit', handleSendMessage);
    resetButton.addEventListener('click', handleReset);
    clearPatientBtn.addEventListener('click', handleClearPatient);

    // Mode Toggle
    patientModeToggle.addEventListener('change', (e) => {
        document.body.classList.toggle('patient-mode', e.target.checked);
        if (e.target.checked) {
            addMessageToChat("Patient Mode Active: Providing simplified, patient-friendly explanations.", "system-message");
        } else {
            addMessageToChat("Clinical Mode Active: Full technical precision enabled.", "system-message");
        }
    });

    // Tab Switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.getAttribute('data-tab');
            switchTab(tab);
            
            // Highlight active tab
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    // Shadow Mode Comparison
    compareShadowBtn.addEventListener('click', handleShadowCompare);

    // Image Upload (OCR)
    imageUpload.addEventListener('change', handleImageOCR);

    // Mic Interaction Mockup
    let isListening = false;
    micBtn.addEventListener('click', () => {
        isListening = !isListening;
        if (isListening) {
            micBtn.classList.add('active');
            micRings.classList.add('animating');
            perceptionStatus.textContent = 'Buddi is listening...';
            perceptionStatus.style.color = '#3fb2d6';
            addMessageToChat('[PERCEPTION] Live audio capture enabled.', 'system-message');
        } else {
            micBtn.classList.remove('active');
            micRings.classList.remove('animating');
            perceptionStatus.textContent = 'Perception Idle';
            perceptionStatus.style.color = 'var(--text-muted)';
            addMessageToChat('[PERCEPTION] Live capture stopped.', 'system-message');
        }
    });

    // Workflow quick-action buttons
    document.querySelectorAll('.workflow-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const message = btn.getAttribute('data-workflow');
            if (message) {
                userInput.value = message;
                chatForm.dispatchEvent(new Event('submit'));
            }
        });
    });

    checkAgentStatus();
    setInterval(checkAgentStatus, RECONNECT_INTERVAL);
});
// ── Agent Status ────────────────────────────────────────────────────

async function checkAgentStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            setAgentStatus(true);
            loadAgentInfo();
            loadPatientContext();
            loadPatientHistory();
            loadRiskAssessment();
            loadAuditLog();
        } else {
            setAgentStatus(false);
        }
    } catch (error) {
        setAgentStatus(false);
        console.warn('Agent API unreachable:', error);
    }
}

function setAgentStatus(connected) {
    agentStatus.connected = connected;
    agentStatus.lastCheckTime = new Date();

    if (connected) {
        statusDot.className = 'status-dot';
        statusText.textContent = 'Connected';
        sendButton.disabled = false;
        document.getElementById('apiStatus').textContent = '✓ API is running';
    } else {
        statusDot.className = 'status-dot error';
        statusText.textContent = 'Disconnected';
        sendButton.disabled = true;
        document.getElementById('apiStatus').textContent = '✗ API is offline';
    }
}

function switchTab(tab) {
    chatContainer.style.display = 'none';
    dashboardView.style.display = 'none';
    shadowView.style.display = 'none';

    if (tab === 'chat') {
        chatContainer.style.display = 'flex';
    } else if (tab === 'dashboard') {
        dashboardView.style.display = 'flex';
        renderRiskHeatmap();
    } else if (tab === 'shadow') {
        shadowView.style.display = 'flex';
    }
}

// ── Agent Info ───────────────────────────────────────────────────────

async function loadAgentInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/status`);
        if (response.ok) {
            const data = await response.json();
            document.getElementById('assistantName').textContent = data.assistant_name || 'N/A';
            document.getElementById('safetyEnabled').textContent = data.safety_enabled ? '✅ Active' : '❌ Disabled';
        }
    } catch (error) {
        console.error('Error loading agent info:', error);
    }
}

// ── Patient Context ─────────────────────────────────────────────────

async function loadPatientContext() {
    try {
        const response = await fetch(`${API_BASE_URL}/patient-context`);
        if (response.ok) {
            const data = await response.json();
            const ctx = data.patient_context;
            const display = document.getElementById('patientContextDisplay');

            if (ctx && ctx.patient_id) {
                display.innerHTML = `
                    <div class="patient-info">
                        <p><strong>${ctx.name || 'Unknown'}</strong></p>
                        <p class="patient-detail">ID: ${ctx.patient_id}</p>
                        ${ctx.conditions && ctx.conditions.length ? `<p class="patient-detail">Dx: ${ctx.conditions.join(', ')}</p>` : ''}
                        ${ctx.medications && ctx.medications.length ? `<p class="patient-detail">Meds: ${ctx.medications.join(', ')}</p>` : ''}
                        ${ctx.allergies && ctx.allergies.length ? `<p class="patient-detail allergy">⚠ Allergies: ${ctx.allergies.join(', ')}</p>` : ''}
                    </div>
                `;
            } else {
                display.innerHTML = '<p class="context-empty">No patient set</p>';
            }
        }
    } catch (error) {
        console.error('Error loading patient context:', error);
    }
}

async function loadPatientHistory() {
    try {
        const response = await fetch(`${API_BASE_URL}/patient-history?count=5`);
        if (response.ok) {
            const data = await response.json();
            const display = document.getElementById('patientHistoryDisplay');
            if (data.history && data.history.length > 0) {
                display.innerHTML = data.history.map(item => `
                    <div class="history-item">
                        <div class="history-item-header">
                            <span>User query</span>
                        </div>
                        <div class="history-item-content">${item.user}</div>
                    </div>
                `).join('');
            } else {
                display.innerHTML = '<p class="context-empty">No history available</p>';
            }
        }
    } catch (error) {
        console.error('Error loading patient history:', error);
    }
}

async function loadRiskAssessment() {
    try {
        const response = await fetch(`${API_BASE_URL}/risk-assessment`);
        if (response.ok) {
            const data = await response.json();
            const container = document.getElementById('riskIndicatorContainer');
            if (data.risks && data.risks.length > 0) {
                container.innerHTML = data.risks.map(r => `
                    <span class="risk-badge ${r.level}">${r.label.split('—')[0].trim()}</span>
                `).join('');
            } else {
                container.innerHTML = '';
            }
            // If the dashboard is visible, update the heatmap too
            if (dashboardView.style.display !== 'none') {
                renderRiskHeatmap(data.risks);
            }
        }
    } catch (error) {
        console.error('Error loading risk assessment:', error);
    }
}

function renderRiskHeatmap(risks = []) {
    const heatmap = document.getElementById('riskHeatmap');
    if (!risks || risks.length === 0) {
        heatmap.innerHTML = '<p class="context-empty">No clinical risks detected to visualize.</p>';
        return;
    }

    heatmap.innerHTML = risks.map(r => `
        <div class="heatmap-card">
            <div style="font-weight: 600; font-size: 0.9rem;">${r.label.split('—')[0]}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary);">${r.label.split('—')[1] || ''}</div>
            <div class="heat-level heat-${r.level}"></div>
        </div>
    `).join('');
}

async function handleShadowCompare() {
    const expertAction = expertActionInput.value.trim();
    if (!expertAction) {
        showError('Please enter your manual charting action first.');
        return;
    }

    // We'll use the last user message as the input message
    const historyRes = await fetch(`${API_BASE_URL}/patient-history?count=1`);
    const history = await historyRes.json();
    const lastMessage = (history.history && history.history.length > 0) 
        ? history.history[0].user 
        : "Patient presents for routine follow-up.";

    showLoading(true);
    try {
        const response = await fetch(`${API_BASE_URL}/shadow-mode/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: lastMessage,
                expert_action: expertAction
            })
        });

        if (!response.ok) throw new Error('Shadow mode comparison failed');
        
        const data = await response.json();
        renderShadowComparison(data);
    } catch (error) {
        showError(error.message);
    } finally {
        showLoading(false);
    }
}

function renderShadowComparison(data) {
    shadowComparisonOutput.innerHTML = `
        <div class="comparison-result">
            <div class="comparison-stat">
                <h3>Intent Match</h3>
                <span class="match-badge match-${data.match}">${data.match ? 'MATCHED' : 'DIVERGED'}</span>
            </div>
            <div class="comparison-stat">
                <h4>Agent Intent Detection</h4>
                <p style="font-size: 0.85rem; color: var(--primary-light);">${data.agent_suggestion}</p>
            </div>
            <div class="comparison-stat">
                <h4>Expert Baseline</h4>
                <p style="font-size: 0.85rem; color: var(--text-secondary);">${data.expert_baseline}</p>
            </div>
        </div>
    `;
}

async function handleImageOCR(event) {
    const file = event.target.files[0];
    if (!file) return;

    showLoading(true);
    addMessageToChat(`[SYSTEM] Initializing Medical OCR for ${file.name}...`, 'system-message');
    
    // In a prototype, we simulate the OCR processing time
    setTimeout(() => {
        showLoading(false);
        const mockOcrText = "MEDICAL RECORD EXTRACT:\nPatient: John Smith\nID: 12345\nConditions: T2DM, Hypertension\nLab: HbA1c 7.7 (2026-03-20)\nNote: Patient reports mild tingling in feet.";
        userInput.value = `Process this medical record extract: ${mockOcrText}`;
        addMessageToChat(`[OCR COMPLETED] Data extracted from image.`, 'system-message');
    }, 2000);
}

async function handleClearPatient() {
    if (!agentStatus.connected) {
        showError('Agent API is not available');
        return;
    }
    try {
        await fetch(`${API_BASE_URL}/patient-context`, { method: 'DELETE' });
        loadPatientContext();
        addMessageToChat('Patient context cleared.', 'system-message');
    } catch (error) {
        showError(`Failed to clear patient: ${error.message}`);
    }
}

// ── Audit Log ───────────────────────────────────────────────────────

async function loadAuditLog() {
    try {
        const response = await fetch(`${API_BASE_URL}/audit-log?count=5`);
        if (response.ok) {
            const data = await response.json();
            const auditLog = document.getElementById('auditLog');

            if (data.events && data.events.length > 0) {
                auditLog.innerHTML = data.events.map(e => {
                    const time = new Date(e.timestamp).toLocaleTimeString();
                    return `<div class="audit-entry"><span class="audit-time">${time}</span> ${e.event_type}</div>`;
                }).join('');
            } else {
                auditLog.innerHTML = '<p class="context-empty">No activity yet</p>';
            }
        }
    } catch (error) {
        console.error('Error loading audit log:', error);
    }
}

// ── Chat ────────────────────────────────────────────────────────────

async function handleSendMessage(event) {
    event.preventDefault();
    const message = userInput.value.trim();

    if (!message) {
        showError('Please enter a message');
        return;
    }
    if (!agentStatus.connected) {
        showError('Agent API is not available. Please check the backend.');
        return;
    }

    addMessageToChat(message, 'user-message');
    userInput.value = '';
    userInput.focus();
    showLoading(true);
    sendButton.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to get response');
        }

        const data = await response.json();
        addMessageToChat(data.response, 'agent-message');

        // Refresh context panels after each message
        loadPatientContext();
        loadPatientHistory();
        loadRiskAssessment();
        loadAuditLog();
    } catch (error) {
        console.error('Error sending message:', error);
        showError(`Failed to send message: ${error.message}`);
        addMessageToChat(`Error: ${error.message}`, 'system-message');
    } finally {
        showLoading(false);
        sendButton.disabled = false;
        userInput.focus();
    }
}

// ── Reset ───────────────────────────────────────────────────────────

async function handleReset() {
    if (!confirm('Reset the agent? This will clear memory and patient context.')) return;
    if (!agentStatus.connected) {
        showError('Agent API is not available');
        return;
    }

    showLoading(true);
    resetButton.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        if (!response.ok) throw new Error('Failed to reset agent');

        messagesContainer.innerHTML = '';
        addMessageToChat('Agent reset. Memory and patient context cleared.', 'system-message');
        loadPatientContext();
        loadAuditLog();
    } catch (error) {
        showError(`Failed to reset: ${error.message}`);
    } finally {
        showLoading(false);
        resetButton.disabled = false;
    }
}

// ── Helpers ─────────────────────────────────────────────────────────

function addMessageToChat(text, className) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${className}`;

    if (className.includes('system-message')) {
        messageDiv.innerHTML = `
            <div class="system-icon-wrapper"><i class="ph-fill ph-sparkle"></i></div>
            <pre class="message-content" style="font-family: inherit; margin: 0;">${text}</pre>
        `;
    } else {
        const pre = document.createElement('pre');
        pre.className = 'message-content';
        pre.textContent = text;
        messageDiv.appendChild(pre);
    }
    
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function showLoading(show) {
    const spinner = document.getElementById('loadingSpinner');
    if (show) {
        spinner.classList.add('active');
    } else {
        spinner.classList.remove('active');
    }
}

function showError(message) {
    toastMessage.textContent = message;
    errorToast.classList.add('show');
    setTimeout(() => { errorToast.classList.remove('show'); }, 5000);
}

userInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

console.log('Buddi Clinical Agent Web UI initialized');
