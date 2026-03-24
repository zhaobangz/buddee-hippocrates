/**
 * Buddi Clinical Agent — Web UI Frontend Logic
 * Healthcare Workflow Intelligence
 */

// Configuration
const API_BASE_URL = 'http://localhost:8000/api';
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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing Buddi Clinical Agent Web UI...');

    chatForm.addEventListener('submit', handleSendMessage);
    resetButton.addEventListener('click', handleReset);
    clearPatientBtn.addEventListener('click', handleClearPatient);

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

    const pre = document.createElement('pre');
    pre.className = 'message-content';
    pre.textContent = text;
    messageDiv.appendChild(pre);
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
