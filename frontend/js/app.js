/**
 * Web-Pennmush Main Application
 * Author: Jordan Koch (GitHub: kochj23)
 * Main application logic and initialization
 */

// Global state
let currentPlayer = null;

/**
 * Initialize the application
 */
function init() {
    console.log('Initializing Web-Pennmush...');

    // Show login modal
    showModal('login-modal');

    // Set up WebSocket event handlers
    setupWebSocketHandlers();

    // Set up input handlers
    setupInputHandlers();

    // Connect to WebSocket
    wsManager.connect();

    // Welcome message
    addOutput('=== Welcome to Web-Pennmush ===');
    addOutput('A modern web-based MUSH server inspired by PennMUSH');
    addOutput('Please log in to begin your adventure.');
    addOutput('');
}

/**
 * Set up WebSocket message handlers
 */
function setupWebSocketHandlers() {
    // Handle authentication required
    wsManager.on('auth_required', (data) => {
        console.log('Authentication required');
        showModal('login-modal');
    });

    // Handle welcome message
    wsManager.on('welcome', (data) => {
        console.log('Welcome message received:', data);
        currentPlayer = {
            id: data.player_id,
            name: data.player_name
        };

        updatePlayerName(data.player_name);
        hideModal('login-modal');
        setInputEnabled(true);

        addOutput('');
        addOutput(data.message);
        addOutput('Type "help" for a list of commands.');
        addOutput('');

        addActivity(`${data.player_name} connected`);

        // Refresh players list
        refreshPlayersList();
    });

    // Handle output from server
    wsManager.on('output', (data) => {
        addOutput('');
        addOutput(data.message);
        addOutput('');
    });

    // Handle errors
    wsManager.on('error', (data) => {
        addOutput(`ERROR: ${data.message}`, 'error');
    });

    // Handle disconnect
    wsManager.onDisconnect = () => {
        setInputEnabled(false);
        currentPlayer = null;
        updatePlayerName('');
        addOutput('');
        addOutput('=== Disconnected from server ===');
        addOutput('');
    };
}

/**
 * Set up input event handlers
 */
function setupInputHandlers() {
    const commandInput = document.getElementById('command-input');
    const sendButton = document.getElementById('send-button');

    // Enter key sends command
    if (commandInput) {
        commandInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendCurrentCommand();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                navigateHistory('up');
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                navigateHistory('down');
            }
        });

        // Focus input on page load
        commandInput.focus();
    }

    // Send button click
    if (sendButton) {
        sendButton.addEventListener('click', sendCurrentCommand);
    }
}

/**
 * Send command from input field
 */
function sendCurrentCommand() {
    const commandInput = document.getElementById('command-input');
    if (!commandInput) return;

    const command = commandInput.value.trim();
    if (!command) return;

    // Add to history
    addToHistory(command);

    // Echo command
    addOutput(`> ${command}`);

    // Send to server
    sendCommand(command);

    // Clear input
    commandInput.value = '';
}

/**
 * Send a command to the server
 */
function sendCommand(command) {
    if (!wsManager.authenticated) {
        addOutput('ERROR: Not connected to server');
        return;
    }

    wsManager.sendCommand(command);
}

/**
 * Handle login form submission
 */
async function handleLogin(event) {
    event.preventDefault();

    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    try {
        await wsManager.authenticate(username, password);
        // Success is handled by the 'welcome' message handler
    } catch (error) {
        showError('login-error', error.message);
    }
}

/**
 * Handle register form submission
 */
async function handleRegister(event) {
    event.preventDefault();

    const username = document.getElementById('register-username').value;
    const password = document.getElementById('register-password').value;
    const email = document.getElementById('register-email').value;

    try {
        const response = await fetch('/api/players/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username: username,
                password: password,
                email: email || null
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Registration failed');
        }

        const data = await response.json();

        // Show success message
        addOutput(`Account created: ${data.name}`);

        // Auto-login
        try {
            await wsManager.authenticate(username, password);
        } catch (error) {
            showError('register-error', 'Account created but login failed. Please try logging in manually.');
        }
    } catch (error) {
        showError('register-error', error.message);
    }
}

/**
 * Refresh players list from server
 */
async function refreshPlayersList() {
    try {
        const response = await fetch('/api/players');
        if (response.ok) {
            const players = await response.json();
            const onlinePlayers = players.filter(p => p.is_connected);
            updatePlayersList(onlinePlayers);
        }
    } catch (error) {
        console.error('Error fetching players list:', error);
    }
}

/**
 * Get server stats
 */
async function getServerStats() {
    try {
        const response = await fetch('/api/stats');
        if (response.ok) {
            const stats = await response.json();
            let output = '=== Server Statistics ===\n';
            for (const [key, value] of Object.entries(stats)) {
                output += `${key}: ${value}\n`;
            }
            addOutput(output);
        }
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', init);

// Refresh players list every 30 seconds
setInterval(() => {
    if (wsManager.authenticated) {
        refreshPlayersList();
    }
}, 30000);

// Prevent accidental page unload
window.addEventListener('beforeunload', (e) => {
    if (wsManager.authenticated) {
        e.preventDefault();
        e.returnValue = 'You are currently connected to the MUSH. Are you sure you want to leave?';
        return e.returnValue;
    }
});
