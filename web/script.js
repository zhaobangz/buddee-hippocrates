/**
 * Buddi Clinical Agent — Premium Web UI Frontend Logic
 * Healthcare Workflow Intelligence
 */

// Configuration
const DEFAULT_API_PORT = 8000;
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? `${window.location.protocol}//${window.location.hostname}:${DEFAULT_API_PORT}/api`
    : '/api';

const RECONNECT_INTERVAL = 5000;

// State
let agentStatus = { connected: false, lastCheckTime: null };
let isListening = false;

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
    console.log('Initializing Buddi Premium UI...');

    chatForm.addEventListener('submit', handleSendMessage);
    resetButton.addEventListener('click', handleReset);
    clearPatientBtn.addEventListener('click', handleClearPatient);

    // Mode Toggle
    patientModeToggle.addEventListener('change', (e) => {
        if (e.target.checked) {
            addMessageToChat("Patient Mode Active: Providing simplified, patient-friendly explanations.", "system");
        } else {
            addMessageToChat("Clinical Mode Active: Full technical precision enabled.", "system");
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

    // Image Upload (OCR Mockup)
    imageUpload.addEventListener('change', handleImageOCR);

    // Mic Interaction
    micBtn.addEventListener('click', () => {
        isListening = !isListening;
        if (isListening) {
            micBtn.classList.add('active');
            micRings.classList.add('animating');
            perceptionStatus.textContent = 'Buddi is listening...';
            addMessageToChat('Live audio capture enabled. Speak clearly.', 'system');
        } else {
            micBtn.classList.remove('active');
            micRings.classList.remove('animating');
            perceptionStatus.textContent = 'Awaiting input...';
            addMessageToChat('Live capture stopped.', 'system');
        }
    });

    // Workflow quick-action chips
    document.querySelectorAll('.chip').forEach(btn => {
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
    }
}

function setAgentStatus(connected) {
    agentStatus.connected = connected;
    agentStatus.lastCheckTime = new Date();

    if (connected) {
        statusDot.classList.add('online');
        statusText.textContent = 'System Online';
        statusText.style.color = 'var(--primary)';
        sendButton.disabled = false;
        document.getElementById('apiStatus').textContent = 'ACTIVE';
        document.getElementById('apiStatus').classList.add('status-tag');
    } else {
        statusDot.classList.remove('online');
        statusText.textContent = 'System Offline';
        statusText.style.color = 'var(--danger)';
        sendButton.disabled = true;
        document.getElementById('apiStatus').textContent = 'OFFLINE';
        document.getElementById('apiStatus').classList.remove('status-tag');
    }
}

function switchTab(tab) {
    chatContainer.classList.remove('active');
    dashboardView.classList.remove('active');
    shadowView.classList.remove('active');
    document.getElementById('historyView').classList.remove('active');
    
    chatContainer.style.display = 'none';
    dashboardView.style.display = 'none';
    shadowView.style.display = 'none';
    document.getElementById('historyView').style.display = 'none';

    if (tab === 'chat') {
        chatContainer.classList.add('active');
        chatContainer.style.display = 'flex';
    } else if (tab === 'dashboard') {
        dashboardView.classList.add('active');
        dashboardView.style.display = 'flex';
        renderRiskHeatmap();
    } else if (tab === 'history') {
        document.getElementById('historyView').classList.add('active');
        document.getElementById('historyView').style.display = 'flex';
        loadPatientHistory();
    } else if (tab === 'shadow') {
        shadowView.classList.add('active');
        shadowView.style.display = 'flex';
    }
}

// ── Agent Info ───────────────────────────────────────────────────────

async function loadAgentInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/status`);
        if (response.ok) {
            const data = await response.json();
            document.getElementById('assistantName').textContent = data.assistant_name || 'Buddi v2';
            document.getElementById('safetyEnabled').textContent = data.safety_enabled ? 'ACTIVE' : 'DISABLED';
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
                        <p><strong>${ctx.name || 'Unknown Patient'}</strong></p>
                        <p class="patient-detail">MRN: ${ctx.patient_id}</p>
                        ${ctx.conditions && ctx.conditions.length ? `<p class="patient-detail">Dx: ${ctx.conditions.join(', ')}</p>` : ''}
                        ${ctx.medications && ctx.medications.length ? `<p class="patient-detail">Rx: ${ctx.medications.join(', ')}</p>` : ''}
                        ${ctx.allergies && ctx.allergies.length ? `<p class="patient-detail allergy">Allergies: ${ctx.allergies.join(', ')}</p>` : ''}
                    </div>
                `;
            } else {
                display.innerHTML = '<p class="empty-state">No patient selected</p>';
            }
        }
    } catch (error) {
        console.error('Error loading patient context:', error);
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
                    <span class="risk-badge ${r.level}">${r.label}</span>
                `).join('');
                
                if (dashboardView.classList.contains('active')) {
                    renderRiskHeatmap(data.risks);
                }
            } else {
                container.innerHTML = '';
            }
        }
    } catch (error) {
        console.error('Error loading risk assessment:', error);
    }
}

async function loadPatientHistory() {
    try {
        const response = await fetch(`${API_BASE_URL}/patient-history?count=15`);
        if (response.ok) {
            const data = await response.json();
            const display = document.getElementById('patientHistoryDisplay');
            if (data.history && data.history.length > 0) {
                display.innerHTML = data.history.map(item => `
                    <div class="history-item">
                        <div class="history-item-header">
                            <span class="history-label"><i class="ph ph-user"></i> USER</span>
                            <span class="history-time">SESSION INTERACTION</span>
                        </div>
                        <div class="history-item-content">${item.user || ''}</div>
                        <div class="history-item-header">
                            <span class="history-label"><i class="ph ph-robot"></i> BUDDI</span>
                        </div>
                        <div class="history-item-content bot">${(item.bot || '').replace(/\n/g, '<br>')}</div>
                    </div>
                `).join('');
            } else {
                display.innerHTML = '<p class="empty-state">No medical history for this session.</p>';
            }
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

function renderRiskHeatmap(risks = []) {
    const heatmap = document.getElementById('riskHeatmap');
    if (!risks || risks.length === 0) {
        heatmap.innerHTML = '<p class="empty-state">No population risk data available.</p>';
        return;
    }

    heatmap.innerHTML = risks.map(r => `
        <div class="heatmap-card">
            <div style="font-weight: 700; font-size: 0.95rem; margin-bottom: 4px;">${r.label}</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary);">Real-time monitoring active</div>
            <div class="heat-level heat-${r.level}"></div>
        </div>
    `).join('');
}

// ── Audit Log ───────────────────────────────────────────────────────

async function loadAuditLog() {
    try {
        const response = await fetch(`${API_BASE_URL}/audit-log?count=8`);
        if (response.ok) {
            const data = await response.json();
            const auditLog = document.getElementById('auditLog');

            if (data.events && data.events.length > 0) {
                auditLog.innerHTML = data.events.map(e => {
                    const time = new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                    return `
                        <div class="audit-entry">
                            <span class="audit-time">${time}</span>
                            <span class="audit-text">${e.event_type}</span>
                        </div>
                    `;
                }).join('');
            } else {
                auditLog.innerHTML = '<p class="empty-state">Audit feed silent</p>';
            }
        }
    } catch (error) {
        console.error('Error loading audit log:', error);
    }
}

// ── Chat Interaction ────────────────────────────────────────────────

async function handleSendMessage(event) {
    event.preventDefault();
    const message = userInput.value.trim();

    if (!message) return;
    if (!agentStatus.connected) {
        showError('System offline. Please wait for reconnection.');
        return;
    }

    addMessageToChat(message, 'user');
    userInput.value = '';
    userInput.style.height = 'auto';
    showLoading(true);

    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }),
        });

        if (!response.ok) throw new Error('API request failed');

        const data = await response.json();
        addMessageToChat(data.response, 'agent');

        // Refresh side panels
        loadPatientContext();
        loadRiskAssessment();
        loadAuditLog();
    } catch (error) {
        showError(`Communication Error: ${error.message}`);
        addMessageToChat(`Fault in connection layer: ${error.message}`, 'system');
    } finally {
        showLoading(false);
    }
}

function addMessageToChat(text, type) {
    const messageNode = document.createElement('div');
    messageNode.className = `message ${type}`;

    if (type === 'system') {
        messageNode.innerHTML = `
            <i class="ph-fill ph-sparkle"></i>
            <div class="message-body">${text}</div>
        `;
    } else {
        messageNode.innerHTML = `
            <div class="message-body">${text}</div>
        `;
    }

    messagesContainer.appendChild(messageNode);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ── Specialized Workflows ───────────────────────────────────────────

async function handleShadowCompare() {
    const expertAction = expertActionInput.value.trim();
    if (!expertAction) {
        showError('Baseline charting required for comparison.');
        return;
    }

    const chatMessages = messagesContainer.querySelectorAll('.message.user');
    const lastUserMessage = chatMessages.length > 0 
        ? chatMessages[chatMessages.length - 1].querySelector('.message-content').textContent 
        : "Initial session state analysis.";

    showLoading(true);
    try {
        const response = await fetch(`${API_BASE_URL}/shadow-mode/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: lastUserMessage,
                expert_action: expertAction
            })
        });

        if (!response.ok) throw new Error('Eval server error');
        
        const data = await response.json();
        shadowComparisonOutput.innerHTML = `
            <div class="comparison-card">
                <div style="margin-bottom: 16px;">
                    <span class="status-tag" style="background: ${data.match ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}; color: ${data.match ? '#10b981' : '#fca5a5'};">
                        ${data.match ? 'VALIDATED' : 'DIVERGENCE DETECTED'}
                    </span>
                </div>
                <p style="font-size: 0.9rem; border-left: 2px solid var(--primary); padding-left: 12px; margin-bottom: 12px;">
                    <strong>Agent Intent:</strong> ${data.agent_suggestion}
                </p>
                <p style="font-size: 0.9rem; color: var(--text-muted);">
                    <strong>Human Baseline:</strong> ${data.expert_baseline}
                </p>
            </div>
        `;
    } catch (error) {
        showError(error.message);
    } finally {
        showLoading(false);
    }
}

async function handleImageOCR(event) {
    const file = event.target.files[0];
    if (!file) return;

    showLoading(true);
    addMessageToChat(`Scanning medical image: ${file.name}...`, 'system');
    
    setTimeout(() => {
        showLoading(false);
        const mockOcrText = "MEDICAL RECORD EXTRACT: Patient John Smith (ID 12345). HbA1c 7.7. T2DM diagnostic history.";
        userInput.value = `Patient data extracted: ${mockOcrText}. Generate clinical summary.`;
    }, 1500);
}

async function handleClearPatient() {
    try {
        await fetch(`${API_BASE_URL}/patient-context`, { method: 'DELETE' });
        loadPatientContext();
        addMessageToChat('Context purged successfully.', 'system');
    } catch (error) {
        showError('Purge failed');
    }
}

async function handleReset() {
    if (!confirm('Execute system reset?')) return;
    showLoading(true);
    try {
        await fetch(`${API_BASE_URL}/reset`, { method: 'POST' });
        messagesContainer.innerHTML = '';
        addMessageToChat('System reset complete. Awaiting new session.', 'system');
        loadPatientContext();
    } catch (error) {
        showError('Reset failed');
    } finally {
        showLoading(false);
    }
}

// ── Global Helpers ──────────────────────────────────────────────────

function showLoading(show) {
    if (show) loadingSpinner.classList.add('active');
    else loadingSpinner.classList.remove('active');
}

function showError(message) {
    toastMessage.textContent = message;
    errorToast.classList.add('show');
    setTimeout(() => errorToast.classList.remove('show'), 4000);
}

console.log('Buddi Core Engine Interface Stable');
