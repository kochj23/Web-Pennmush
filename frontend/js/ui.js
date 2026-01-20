/**
 * Web-Pennmush UI Helper Functions
 * Author: Jordan Koch (GitHub: kochj23)
 * Manages UI updates and interactions
 */

// Command history
let commandHistory = [];
let historyIndex = -1;

/**
 * Add output to the output window
 */
function addOutput(text, className = '') {
    const outputDiv = document.getElementById('output');
    if (!outputDiv) return;

    const messageDiv = document.createElement('div');
    messageDiv.textContent = text;
    if (className) {
        messageDiv.className = className;
    }

    outputDiv.appendChild(messageDiv);

    // Auto-scroll to bottom
    outputDiv.scrollTop = outputDiv.scrollHeight;

    // Parse room info if available
    parseRoomInfo(text);
}

/**
 * Clear the output window
 */
function clearOutput() {
    const outputDiv = document.getElementById('output');
    if (outputDiv) {
        outputDiv.innerHTML = '';
    }
}

/**
 * Parse room information from look command output
 */
function parseRoomInfo(text) {
    // Very basic parsing - in a full implementation, the server would send structured data
    const lines = text.split('\n');

    // Check if this looks like a room description
    if (lines[0] && lines[0].includes('(#')) {
        const roomName = lines[0];
        updateRoomName(roomName);
    }

    // Parse exits
    const exitsMatch = text.match(/Obvious exits: (.+)/);
    if (exitsMatch) {
        const exits = exitsMatch[1].split(',').map(e => e.trim());
        updateExitsList(exits);
    }

    // Parse contents
    const contentsIndex = lines.findIndex(line => line.trim() === 'Contents:');
    if (contentsIndex !== -1) {
        const contents = [];
        for (let i = contentsIndex + 1; i < lines.length; i++) {
            if (lines[i].trim().startsWith('Players:') || lines[i].trim() === '') break;
            if (lines[i].trim()) contents.push(lines[i].trim());
        }
        updateContentsList(contents);
    }
}

/**
 * Update room name display
 */
function updateRoomName(name) {
    const roomNameDiv = document.querySelector('.room-name');
    if (roomNameDiv) {
        roomNameDiv.textContent = name;
    }
}

/**
 * Update exits list
 */
function updateExitsList(exits) {
    const exitsListDiv = document.getElementById('exits-list');
    if (!exitsListDiv) return;

    exitsListDiv.innerHTML = '';
    exits.forEach(exit => {
        const exitDiv = document.createElement('div');
        exitDiv.textContent = `→ ${exit}`;
        exitDiv.style.cursor = 'pointer';
        exitDiv.onclick = () => sendCommand(exit);
        exitsListDiv.appendChild(exitDiv);
    });
}

/**
 * Update contents list
 */
function updateContentsList(contents) {
    const contentsListDiv = document.getElementById('contents-list');
    if (!contentsListDiv) return;

    contentsListDiv.innerHTML = '';
    contents.forEach(item => {
        const itemDiv = document.createElement('div');
        itemDiv.textContent = item;
        contentsListDiv.appendChild(itemDiv);
    });
}

/**
 * Update players list
 */
function updatePlayersList(players) {
    const playersListDiv = document.getElementById('players-list');
    if (!playersListDiv) return;

    if (players.length === 0) {
        playersListDiv.innerHTML = '<div class="no-players">No players online</div>';
        return;
    }

    playersListDiv.innerHTML = '';
    players.forEach(player => {
        const playerDiv = document.createElement('div');
        playerDiv.className = 'player-item';
        playerDiv.innerHTML = `
            <span class="player-status"></span>
            <span>${player.name}</span>
        `;
        playersListDiv.appendChild(playerDiv);
    });
}

/**
 * Add activity log entry
 */
function addActivity(text) {
    const activityLog = document.getElementById('activity-log');
    if (!activityLog) return;

    const activityDiv = document.createElement('div');
    activityDiv.className = 'activity-item';
    activityDiv.textContent = text;

    // Add to top
    activityLog.insertBefore(activityDiv, activityLog.firstChild);

    // Keep only last 20 items
    while (activityLog.children.length > 20) {
        activityLog.removeChild(activityLog.lastChild);
    }
}

/**
 * Show/hide modal
 */
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
    }
}

function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Show/hide tabs
 */
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // Remove active from all buttons
    document.querySelectorAll('.tab-button').forEach(button => {
        button.classList.remove('active');
    });

    // Show selected tab
    const tab = document.getElementById(`${tabName}-tab`);
    if (tab) {
        tab.classList.add('active');
    }

    // Activate button
    const buttons = document.querySelectorAll('.tab-button');
    buttons.forEach(button => {
        if (button.textContent.toLowerCase().includes(tabName)) {
            button.classList.add('active');
        }
    });
}

/**
 * Show error message
 */
function showError(elementId, message) {
    const errorDiv = document.getElementById(elementId);
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.classList.add('show');

        // Auto-hide after 5 seconds
        setTimeout(() => {
            errorDiv.classList.remove('show');
        }, 5000);
    }
}

/**
 * Enable/disable input
 */
function setInputEnabled(enabled) {
    const commandInput = document.getElementById('command-input');
    const sendButton = document.getElementById('send-button');

    if (commandInput) {
        commandInput.disabled = !enabled;
        if (enabled) {
            commandInput.focus();
        }
    }

    if (sendButton) {
        sendButton.disabled = !enabled;
    }
}

/**
 * Add command to history
 */
function addToHistory(command) {
    if (command && command.trim()) {
        commandHistory.push(command);
        if (commandHistory.length > 100) {
            commandHistory.shift(); // Keep only last 100 commands
        }
        historyIndex = commandHistory.length;
    }
}

/**
 * Navigate command history
 */
function navigateHistory(direction) {
    const commandInput = document.getElementById('command-input');
    if (!commandInput || commandHistory.length === 0) return;

    if (direction === 'up') {
        if (historyIndex > 0) {
            historyIndex--;
            commandInput.value = commandHistory[historyIndex];
        }
    } else if (direction === 'down') {
        if (historyIndex < commandHistory.length - 1) {
            historyIndex++;
            commandInput.value = commandHistory[historyIndex];
        } else {
            historyIndex = commandHistory.length;
            commandInput.value = '';
        }
    }
}

/**
 * Update player name display
 */
function updatePlayerName(name) {
    const playerNameSpan = document.getElementById('player-name');
    if (playerNameSpan) {
        playerNameSpan.textContent = name;
    }
}
