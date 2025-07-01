/**
 * Agency Swarm Interactive Visualization
 * Modular JavaScript for SVG-based agency visualization
 */

class AgencyVisualization {
    constructor(agencyData) {
        this.agencyData = agencyData;
        this.showTools = true;
        this.currentZoom = 1;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.dragStart = { x: 0, y: 0 };
        this.draggedNode = null;
        this.nodePositions = new Map();

        // SVG elements
        this.svg = document.getElementById('visualization-svg');
        this.nodesGroup = document.getElementById('nodes-group');
        this.edgesGroup = document.getElementById('edges-group');

        this.init();
    }

    init() {
        console.log('🚀 Initializing Agency Visualization...');

        this.updateStats();
        this.addEventListeners();
        this.initializeNodePositions();
        this.drawVisualization();

        console.log('✅ Visualization initialized successfully');
    }

    addEventListeners() {
        // Canvas pan/zoom handlers
        this.svg.addEventListener('mousedown', (e) => this.startCanvasDrag(e));
        this.svg.addEventListener('mousemove', (e) => this.handleMouseMove(e));
        this.svg.addEventListener('mouseup', () => this.endDrag());
        this.svg.addEventListener('mouseleave', () => this.endDrag());
        this.svg.addEventListener('wheel', (e) => this.zoom(e));

        // Prevent context menu on right-click
        this.svg.addEventListener('contextmenu', (e) => e.preventDefault());

        // Window resize handler
        window.addEventListener('resize', () => this.handleResize());
    }

    initializeNodePositions() {
        // Initialize node positions from the agency data (already positioned by Python)
        this.agencyData.nodes.forEach(node => {
            if (node.position) {
                this.nodePositions.set(node.id, { x: node.position.x, y: node.position.y });
            } else {
                // Fallback position if not provided
                this.nodePositions.set(node.id, { x: 400, y: 300 });
            }
        });
    }



    drawVisualization() {
        // Clear existing content
        this.nodesGroup.innerHTML = '';
        this.edgesGroup.innerHTML = '';

        const nodes = this.showTools ? this.agencyData.nodes : this.agencyData.nodes.filter(n => n.type === 'agent');
        const edges = this.showTools ? this.agencyData.edges : this.agencyData.edges.filter(e => {
            const sourceNode = this.agencyData.nodes.find(n => n.id === e.source);
            const targetNode = this.agencyData.nodes.find(n => n.id === e.target);
            return sourceNode?.type === 'agent' && targetNode?.type === 'agent';
        });

        // Draw edges first (behind nodes)
        edges.forEach(edge => {
            const sourceNode = this.agencyData.nodes.find(n => n.id === edge.source);
            const targetNode = this.agencyData.nodes.find(n => n.id === edge.target);
            if (sourceNode && targetNode) {
                this.drawEdge(sourceNode, targetNode, edge);
            }
        });

        // Draw nodes
        nodes.forEach(node => this.drawNode(node));
    }

    drawNode(node) {
        const currentPos = this.nodePositions.get(node.id) || node.position || { x: 400, y: 300 };
        const isAgent = node.type === 'agent';
        const isEntryPoint = node.data?.isEntryPoint;

        // Create node group
        const nodeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        nodeGroup.setAttribute('transform', `translate(${currentPos.x}, ${currentPos.y})`);
        nodeGroup.setAttribute('data-node-id', node.id);
        nodeGroup.style.cursor = 'move';

        // Create rectangle
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        const width = isAgent ? 120 : 100;
        const height = isAgent ? 60 : 50;

        rect.setAttribute('width', width);
        rect.setAttribute('height', height);
        rect.setAttribute('rx', isAgent ? 12 : 8);
        rect.setAttribute('ry', isAgent ? 12 : 8);
        rect.setAttribute('x', -width / 2);
        rect.setAttribute('y', -height / 2);

        if (isAgent) {
            rect.setAttribute('class', isEntryPoint ? 'node-entry-point' : 'node-agent');
        } else {
            rect.setAttribute('class', 'node-tool');
        }

        // Create text
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', '0');
        text.setAttribute('y', '0');
        text.setAttribute('class', isAgent ? 'node-text' : 'node-text node-text-tool');
        text.textContent = this.truncateText(node.data?.label || node.id, isAgent ? 14 : 12);

        // Add node drag handlers
        nodeGroup.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            this.startNodeDrag(e, node);
        });

        nodeGroup.appendChild(rect);
        nodeGroup.appendChild(text);
        this.nodesGroup.appendChild(nodeGroup);
    }

    drawEdge(sourceNode, targetNode, edge) {
        const sourcePos = this.nodePositions.get(sourceNode.id) || sourceNode.position || { x: 0, y: 0 };
        const targetPos = this.nodePositions.get(targetNode.id) || targetNode.position || { x: 0, y: 0 };

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');

        // Create curved path
        const midX = (sourcePos.x + targetPos.x) / 2;
        const midY = (sourcePos.y + targetPos.y) / 2;
        const controlX = midX;
        const controlY = midY - 30;

        const pathData = `M ${sourcePos.x} ${sourcePos.y} Q ${controlX} ${controlY} ${targetPos.x} ${targetPos.y}`;
        path.setAttribute('d', pathData);

        const isToolEdge = edge.type === 'tool' || sourceNode.type === 'tool' || targetNode.type === 'tool';
        path.setAttribute('class', isToolEdge ? 'edge edge-tool' : 'edge');

        this.edgesGroup.appendChild(path);
    }

    truncateText(text, maxLength) {
        return text.length > maxLength ? text.substring(0, maxLength - 3) + '...' : text;
    }

    // Event handlers
    startCanvasDrag(e) {
        if (e.target.closest('[data-node-id]')) return;

        this.isDragging = true;
        this.draggedNode = null;
        this.dragStart.x = e.clientX - this.panX;
        this.dragStart.y = e.clientY - this.panY;
    }

    startNodeDrag(e, node) {
        this.isDragging = true;
        this.draggedNode = node;

        const rect = this.svg.getBoundingClientRect();
        const svgX = (e.clientX - rect.left - this.panX) / this.currentZoom;
        const svgY = (e.clientY - rect.top - this.panY) / this.currentZoom;

        const currentPos = this.nodePositions.get(node.id);
        this.dragStart.x = svgX - currentPos.x;
        this.dragStart.y = svgY - currentPos.y;
    }

    handleMouseMove(e) {
        if (!this.isDragging) return;

        if (this.draggedNode) {
            const rect = this.svg.getBoundingClientRect();
            const svgX = (e.clientX - rect.left - this.panX) / this.currentZoom;
            const svgY = (e.clientY - rect.top - this.panY) / this.currentZoom;

            const newX = svgX - this.dragStart.x;
            const newY = svgY - this.dragStart.y;

            this.nodePositions.set(this.draggedNode.id, { x: newX, y: newY });
            this.drawVisualization();
        } else {
            this.panX = e.clientX - this.dragStart.x;
            this.panY = e.clientY - this.dragStart.y;
            this.updateTransform();
        }
    }

    endDrag() {
        this.isDragging = false;
        this.draggedNode = null;
    }

    zoom(e) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        this.currentZoom *= delta;
        this.currentZoom = Math.max(0.1, Math.min(3, this.currentZoom));
        this.updateTransform();
    }

    updateTransform() {
        const transform = `translate(${this.panX}, ${this.panY}) scale(${this.currentZoom})`;
        this.nodesGroup.setAttribute('transform', transform);
        this.edgesGroup.setAttribute('transform', transform);
    }

    handleResize() {
        // Handle window resize if needed
        this.drawVisualization();
    }

    updateStats() {
        const visibleNodes = this.showTools ? this.agencyData.nodes : this.agencyData.nodes.filter(n => n.type === 'agent');
        const agents = visibleNodes.filter(n => n.type === 'agent').length;
        const tools = visibleNodes.filter(n => n.type === 'tool').length;
        const flows = this.agencyData.edges.filter(e => e.type === 'communication').length;
        const entryPoints = this.agencyData.metadata?.entryPoints?.length || 0;

        document.getElementById('stats-agents').textContent = `Agents: ${agents}`;
        document.getElementById('stats-tools').textContent = `Tools: ${tools}`;
        document.getElementById('stats-flows').textContent = `Communication Flows: ${flows}`;
        document.getElementById('stats-entry-points').textContent = `Entry Points: ${entryPoints}`;
    }

    // Public API methods
    toggleTools() {
        this.showTools = !this.showTools;
        const btn = document.getElementById('btn-tools');
        btn.textContent = this.showTools ? 'Hide Tools' : 'Show Tools';
        this.drawVisualization();
        this.updateStats();
    }

    fitView() {
        this.currentZoom = 1;
        this.panX = 0;
        this.panY = 0;
        this.updateTransform();
    }

    resetZoom() {
        this.currentZoom = 1;
        this.panX = 0;
        this.panY = 0;
        this.updateTransform();
    }

    zoomIn() {
        this.currentZoom *= 1.2;
        this.currentZoom = Math.min(3, this.currentZoom);
        this.updateTransform();
    }

    zoomOut() {
        this.currentZoom *= 0.8;
        this.currentZoom = Math.max(0.1, this.currentZoom);
        this.updateTransform();
    }


}

// Global variables and functions for HTML compatibility
let visualization;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (typeof agencyData !== 'undefined') {
        visualization = new AgencyVisualization(agencyData);
    } else {
        console.error('Agency data not found. Make sure the data is properly injected.');
    }
});

// Global functions for HTML onclick handlers
function toggleTools() {
    visualization?.toggleTools();
}

function fitView() {
    visualization?.fitView();
}

function resetZoom() {
    visualization?.resetZoom();
}

function zoomIn() {
    visualization?.zoomIn();
}

function zoomOut() {
    visualization?.zoomOut();
}
