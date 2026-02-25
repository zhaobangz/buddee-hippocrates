/**
 * Buddi Agent Web UI - Frontend Logic
 * Handles communication with the FastAPI backend
 */

// Configuration
const API_BASE_URL = 'http://localhost:8000/api';
const RECONNECT_INTERVAL = 5000; // milliseconds

// State
let agentStatus = {
    connected: false,
    lastCheckTime: null
};

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
const includeHistoryCheckbox = document.getElementById('includeHistory');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing Buddi Agent Web UI...');
    
    // Setup event listeners
    chatForm.addEventListener('submit', handleSendMessage);
    resetButton.addEventListener('click', handleReset);
    
    // Initial status check
    checkAgentStatus();
    
    // Periodic status checks
    setInterval(checkAgentStatus, RECONNECT_INTERVAL);
});

/**
 * Check if the agent API is available
 */
async function checkAgentStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        
        if (response.ok) {
            setAgentStatus(true);
            loadAgentInfo();
        } else {
            setAgentStatus(false);
        }
    } catch (error) {
        setAgentStatus(false);
        console.warn('Agent API unreachable:', error);
    }
}

/**
 * Update UI based on agent status
 */
function setAgentStatus(connected) {
    agentStatus.connected = connected;
    agentStatus.lastCheckTime = new Date();
    
    const statusElement = document.getElementById('statusDot');
    const statusTextElement = document.getElementById('statusText');
    
    if (connected) {
        statusElement.textContent = '';
        statusElement.className = 'status-dot';
        statusTextElement.textContent = 'Connected';
        sendButton.disabled = false;
        document.getElementById('apiStatus').textContent = '✓ API is running';
    } else {
        statusElement.className = 'status-dot error';
        statusTextElement.textContent = 'Disconnected';
        sendButton.disabled = true;
        document.getElementById('apiStatus').textContent = '✗ API is offline';
    }
}

/**
 * Load agent information and display in sidebar
 */
async function loadAgentInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/status`);
        
        if (response.ok) {
            const data = await response.json();
            
            document.getElementById('assistantName').textContent = data.assistant_name || 'N/A';
            document.getElementById('memoryEnabled').textContent = data.memory_enabled ? 'Yes' : 'No';
            document.getElementById('voiceMode').textContent = data.use_voice ? 'Enabled' : 'Disabled';
        }
    } catch (error) {
        console.error('Error loading agent info:', error);
    }
}

/**
 * Handle sending a message
 */
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
    
    // Add user message to chat
    addMessageToChat(message, 'user-message');
    
    // Clear input
    userInput.value = '';
    userInput.focus();
    
    // Show loading spinner
    showLoading(true);
    sendButton.disabled = true;
    
    try {
        // Send message to API
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                include_history: includeHistoryCheckbox.checked
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to get response');
        }
        
        const data = await response.json();
        
        // Add agent response to chat
        addMessageToChat(data.response, 'agent-message');
        
    } catch (error) {
        console.error('Error sending message:', error);
        showError(`Failed to send message: ${error.message}`);
        
        // Add error message to chat
        addMessageToChat(
            `Error: Unable to process your message. ${error.message}`,
            'system-message'
        );
    } finally {
        showLoading(false);
        sendButton.disabled = false;
        userInput.focus();
    }
}

/**
 * Handle reset agent
 */
async function handleReset() {
    if (!confirm('Are you sure you want to clear the agent\'s memory? This cannot be undone.')) {
        return;
    }
    
    if (!agentStatus.connected) {
        showError('Agent API is not available');
        return;
    }
    
    showLoading(true);
    resetButton.disabled = true;
    
    try {
        const response = await fetch(`${API_BASE_URL}/reset`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to reset agent');
        }
        
        // Clear chat messages
        messagesContainer.innerHTML = '';
        addMessageToChat('Memory cleared. Hello again!', 'system-message');
        
        console.log('Agent memory reset successfully');
        
    } catch (error) {
        console.error('Error resetting agent:', error);
        showError(`Failed to reset: ${error.message}`);
    } finally {
        showLoading(false);
        resetButton.disabled = false;
    }
}

/**
 * Add a message to the chat UI
 */
function addMessageToChat(text, className) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${className}`;
    
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    
    messageDiv.appendChild(paragraph);
    messagesContainer.appendChild(messageDiv);
    
    // Auto-scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

/**
 * Show loading spinner
 */
function showLoading(show) {
    const spinner = document.getElementById('loadingSpinner');
    
    if (show) {
        spinner.classList.add('active');
    } else {
        spinner.classList.remove('active');
    }
}

/**
 * Show error toast
 */
function showError(message) {
    toastMessage.textContent = message;
    errorToast.classList.add('show');
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        errorToast.classList.remove('show');
    }, 5000);
}

/**
 * Allow Enter key to send message (Shift+Enter for newline)
 */
userInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

// Utility: Format timestamp
function formatTime(date) {
    return new Intl.DateTimeFormat('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    }).format(date);
}

// Log initialization complete
console.log('Buddi Agent Web UI initialized');
