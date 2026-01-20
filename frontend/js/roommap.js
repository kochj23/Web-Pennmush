/**
 * Web-Pennmush Room Map Visualization
 * Author: Jordan Koch (GitHub: kochj23)
 * Uses D3.js for graph visualization
 */

class RoomMapVisualizer {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        this.width = 400;
        this.height = 400;
        this.svg = null;
        this.simulation = null;
        this.currentRoomId = null;
    }

    /**
     * Initialize the SVG canvas
     */
    init() {
        if (!this.container) return;

        this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this.svg.setAttribute('width', this.width);
        this.svg.setAttribute('height', this.height);
        this.svg.style.border = '1px solid var(--border-color)';
        this.svg.style.borderRadius = '8px';
        this.svg.style.background = 'var(--bg-tertiary)';
        this.container.innerHTML = '';
        this.container.appendChild(this.svg);
    }

    /**
     * Load and visualize room map from API
     */
    async loadMap(centerRoomId = 0, radius = 5) {
        try {
            const response = await fetch(`/api/rooms/map?center_room_id=${centerRoomId}&radius=${radius}`);
            if (!response.ok) {
                throw new Error('Failed to load room map');
            }

            const data = await response.json();
            this.visualize(data);
        } catch (error) {
            console.error('Error loading room map:', error);
            this.showError('Failed to load room map');
        }
    }

    /**
     * Visualize the room graph
     */
    visualize(data) {
        if (!this.svg) this.init();

        // Clear previous visualization
        this.svg.innerHTML = '';

        const nodes = data.nodes;
        const edges = data.edges;

        if (nodes.length === 0) {
            this.showError('No rooms to display');
            return;
        }

        // Simple force-directed layout simulation (without D3.js library)
        // We'll use a basic circular layout for simplicity
        const centerX = this.width / 2;
        const centerY = this.height / 2;
        const radius = Math.min(this.width, this.height) * 0.35;

        // Position nodes in a circle
        nodes.forEach((node, index) => {
            const angle = (index / nodes.length) * 2 * Math.PI;
            node.x = centerX + radius * Math.cos(angle);
            node.y = centerY + radius * Math.sin(angle);
        });

        // Draw edges
        edges.forEach(edge => {
            const source = nodes.find(n => n.id === edge.source);
            const target = nodes.find(n => n.id === edge.target);

            if (source && target) {
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', source.x);
                line.setAttribute('y1', source.y);
                line.setAttribute('x2', target.x);
                line.setAttribute('y2', target.y);
                line.setAttribute('stroke', '#4a5568');
                line.setAttribute('stroke-width', '2');
                line.setAttribute('opacity', '0.6');
                this.svg.appendChild(line);
            }
        });

        // Draw nodes
        nodes.forEach(node => {
            const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            group.style.cursor = 'pointer';

            // Circle
            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('cx', node.x);
            circle.setAttribute('cy', node.y);
            circle.setAttribute('r', 15);
            circle.setAttribute('fill', node.id === data.center ? '#00ff88' : '#2d3748');
            circle.setAttribute('stroke', '#00ff88');
            circle.setAttribute('stroke-width', '2');

            // Label
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', node.x);
            text.setAttribute('y', node.y + 25);
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('fill', '#e0e0e0');
            text.setAttribute('font-size', '10');
            text.textContent = node.name.substring(0, 12);

            // Tooltip
            const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = `${node.name} (#${node.id})`;

            group.appendChild(circle);
            group.appendChild(text);
            group.appendChild(title);

            // Click handler
            group.addEventListener('click', () => {
                addOutput(`Viewing room: ${node.name} (#${node.id})`);
                sendCommand(`look`);
            });

            this.svg.appendChild(group);
        });
    }

    /**
     * Show error message
     */
    showError(message) {
        if (!this.container) return;
        this.container.innerHTML = `<div style="padding: 1rem; color: var(--error-color); text-align: center;">${message}</div>`;
    }

    /**
     * Update current room highlight
     */
    updateCurrentRoom(roomId) {
        this.currentRoomId = roomId;
        this.loadMap(roomId);
    }
}

// Create global room map visualizer
const roomMapVisualizer = new RoomMapVisualizer('#room-map-container');
