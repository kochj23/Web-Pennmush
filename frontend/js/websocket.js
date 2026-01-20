/**
 * Web-Pennmush WebSocket Manager
 * Author: Jordan Koch (GitHub: kochj23)
 * Handles WebSocket connection and message routing
 */

class WebSocketManager {
    constructor() {
        this.ws = null;
        this.connected = false;
        this.authenticated = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.messageHandlers = {};
        this.onConnect = null;
        this.onDisconnect = null;
        this.onError = null;
    }

    /**
     * Connect to the WebSocket server
     */
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        console.log('Connecting to WebSocket:', wsUrl);

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.connected = true;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus('connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            if (this.onError) {
                this.onError(error);
            }
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.connected = false;
            this.authenticated = false;
            this.updateConnectionStatus('disconnected');

            if (this.onDisconnect) {
                this.onDisconnect();
            }

            // Attempt to reconnect
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.log(`Reconnecting in ${this.reconnectDelay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                setTimeout(() => this.connect(), this.reconnectDelay);
            } else {
                addOutput('Connection lost. Please refresh the page to reconnect.');
            }
        };
    }

    /**
     * Authenticate with the server
     */
    authenticate(username, password) {
        return new Promise((resolve, reject) => {
            if (!this.connected) {
                reject(new Error('Not connected to server'));
                return;
            }

            // Set up one-time handlers for auth response
            const authHandler = (data) => {
                if (data.type === 'welcome') {
                    this.authenticated = true;
                    resolve(data);
                } else if (data.type === 'error') {
                    reject(new Error(data.message));
                }
            };

            this.on('welcome', authHandler);
            this.on('error', authHandler);

            // Send authentication
            this.send({
                type: 'auth',
                username: username,
                password: password
            });
        });
    }

    /**
     * Send a command to the server
     */
    sendCommand(command) {
        if (!this.authenticated) {
            console.error('Not authenticated');
            return;
        }

        this.send({
            type: 'command',
            command: command
        });
    }

    /**
     * Send raw data to the server
     */
    send(data) {
        if (!this.connected || !this.ws) {
            console.error('WebSocket not connected');
            return;
        }

        this.ws.send(JSON.stringify(data));
    }

    /**
     * Handle incoming messages
     */
    handleMessage(data) {
        const type = data.type;

        if (this.messageHandlers[type]) {
            this.messageHandlers[type].forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in message handler for ${type}:`, error);
                }
            });
        }
    }

    /**
     * Register a message handler
     */
    on(type, handler) {
        if (!this.messageHandlers[type]) {
            this.messageHandlers[type] = [];
        }
        this.messageHandlers[type].push(handler);
    }

    /**
     * Remove a message handler
     */
    off(type, handler) {
        if (this.messageHandlers[type]) {
            this.messageHandlers[type] = this.messageHandlers[type].filter(h => h !== handler);
        }
    }

    /**
     * Update connection status UI
     */
    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connection-status');
        if (statusElement) {
            if (status === 'connected') {
                statusElement.textContent = 'Connected';
                statusElement.className = 'status-connected';
            } else {
                statusElement.textContent = 'Disconnected';
                statusElement.className = 'status-disconnected';
            }
        }
    }

    /**
     * Disconnect from the server
     */
    disconnect() {
        if (this.ws) {
            this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect
            this.ws.close();
        }
    }

    /**
     * Send ping to keep connection alive
     */
    ping() {
        if (this.connected) {
            this.send({ type: 'ping' });
        }
    }
}

// Create global WebSocket manager instance
const wsManager = new WebSocketManager();

// Keep connection alive with periodic pings
setInterval(() => {
    wsManager.ping();
}, 30000); // Ping every 30 seconds
