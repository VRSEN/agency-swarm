#!/usr/bin/env python3
"""
ReactFlow Integration Example

This example demonstrates how to integrate Agency Swarm visualization
with ReactFlow in a web application. It generates a complete HTML page
with interactive ReactFlow components.
"""

import json
import os
import sys
import webbrowser
from pathlib import Path

# Add the src directory to the path so we can import agency_swarm
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agency_swarm import Agency, Agent, BaseTool


class ExampleTool(BaseTool):
    """Example tool for demonstration"""

    def __init__(self):
        super().__init__(name="ExampleTool", description="An example tool for visualization demo")

    def run(self, **kwargs):
        return "Example tool executed"


class CEOAgent(Agent):
    """CEO Agent - the entry point of the agency"""

    def __init__(self):
        super().__init__(
            name="CEO",
            description="Chief Executive Officer - oversees all operations",
            instructions="You are the CEO responsible for high-level decision making and coordination.",
            tools=[],
        )


class ProjectManagerAgent(Agent):
    """Project Manager Agent"""

    def __init__(self):
        super().__init__(
            name="ProjectManager",
            description="Manages project timelines and coordinates between teams",
            instructions="You manage projects, timelines, and coordinate between different teams.",
            tools=[ExampleTool()],
        )


class DeveloperAgent(Agent):
    """Developer Agent"""

    def __init__(self):
        super().__init__(
            name="Developer",
            description="Writes and maintains code",
            instructions="You write, test, and maintain code for various projects.",
            tools=[ExampleTool()],
        )


class QAAgent(Agent):
    """Quality Assurance Agent"""

    def __init__(self):
        super().__init__(
            name="QA",
            description="Tests software and ensures quality",
            instructions="You test software, find bugs, and ensure quality standards.",
            tools=[ExampleTool()],
        )


def create_demo_agency():
    """Create the same demo agency as the first example for consistency"""

    # Create agents (same as first example)
    ceo = CEOAgent()
    pm = ProjectManagerAgent()
    dev = DeveloperAgent()
    qa = QAAgent()

    # Create agency with communication flows (v1.x pattern)
    agency = Agency(
        ceo,  # Entry point agent (positional argument)
        communication_flows=[
            (ceo, pm),  # CEO can communicate with PM
            (pm, dev),  # PM can communicate with Developer
            (pm, qa),  # PM can communicate with QA
            (dev, qa),  # Developer can communicate with QA
        ],
        shared_instructions="This is a software development agency with clear hierarchy and communication flows.",
    )

    return agency


def generate_reactflow_html(agency_data, output_file="agency_reactflow_visualization.html"):
    """Generate a complete HTML page with interactive visualization using SVG"""

    # Convert agency data to JSON string for embedding
    agency_json = json.dumps(agency_data, indent=2)

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agency Swarm - Interactive Visualization</title>
    <style>
        body {{
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
                'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
                sans-serif;
            background-color: #f5f5f5;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}

        .header h1 {{
            margin: 0;
            font-size: 2rem;
        }}

        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}

        .container {{
            display: flex;
            height: calc(100vh - 120px);
        }}

        .visualization-wrapper {{
            flex: 1;
            background: white;
            margin: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            overflow: hidden;
            position: relative;
        }}

        .controls {{
            width: 300px;
            background: white;
            margin: 20px 20px 20px 0;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            padding: 20px;
            overflow-y: auto;
        }}

        .control-group {{
            margin-bottom: 20px;
        }}

        .control-group h3 {{
            margin: 0 0 10px 0;
            color: #333;
            font-size: 1.1rem;
        }}

        .control-group button {{
            width: 100%;
            padding: 10px;
            margin: 5px 0;
            border: none;
            border-radius: 6px;
            background: #667eea;
            color: white;
            cursor: pointer;
            font-size: 14px;
            transition: background-color 0.2s;
        }}

        .control-group button:hover {{
            background: #5a6fd8;
        }}

        .control-group button.active {{
            background: #764ba2;
        }}

        .stats {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin-top: 20px;
        }}

        .stats h4 {{
            margin: 0 0 10px 0;
            color: #333;
        }}

        .stats div {{
            margin: 5px 0;
            color: #666;
        }}

        /* SVG Visualization Styles */
        #visualization-svg {{
            width: 100%;
            height: 100%;
            cursor: grab;
        }}

        #visualization-svg:active {{
            cursor: grabbing;
        }}

        .node-agent {{
            fill: url(#agentGradient);
            stroke: #5a6fd8;
            stroke-width: 2;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .node-agent:hover {{
            stroke-width: 3;
            filter: drop-shadow(0 4px 8px rgba(102, 126, 234, 0.4));
        }}

        .node-tool {{
            fill: url(#toolGradient);
            stroke: #e17055;
            stroke-width: 2;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .node-tool:hover {{
            stroke-width: 3;
            filter: drop-shadow(0 3px 6px rgba(255, 167, 138, 0.4));
        }}

        .node-entry-point {{
            fill: url(#entryGradient);
            stroke: #00a085;
            stroke-width: 3;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .node-entry-point:hover {{
            stroke-width: 4;
            filter: drop-shadow(0 4px 12px rgba(0, 184, 148, 0.5));
        }}

        .node-text {{
            fill: white;
            font-size: 12px;
            font-weight: bold;
            text-anchor: middle;
            dominant-baseline: middle;
            pointer-events: none;
        }}

        .node-text-tool {{
            fill: #2d3436;
        }}

        .edge {{
            stroke: #667eea;
            stroke-width: 2;
            fill: none;
            marker-end: url(#arrowhead);
        }}

        .edge-tool {{
            stroke: #fab1a0;
            stroke-width: 1.5;
            stroke-dasharray: 5,5;
        }}

        .zoom-controls {{
            position: absolute;
            top: 10px;
            right: 10px;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }}

        .zoom-btn {{
            width: 40px;
            height: 40px;
            border: none;
            border-radius: 6px;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            cursor: pointer;
            font-size: 18px;
            font-weight: bold;
            color: #667eea;
            transition: all 0.2s;
        }}

        .zoom-btn:hover {{
            background: #f8f9fa;
            transform: scale(1.05);
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Agency Swarm Visualization</h1>
        <p>Interactive visualization of agent communication flows and tool relationships</p>
    </div>

    <div class="container">
        <div class="controls">
            <div class="control-group">
                <h3>Layout Algorithms</h3>
                <button onclick="updateLayout('hierarchical')" class="active" id="btn-hierarchical">Hierarchical</button>
                <button onclick="updateLayout('circular')" id="btn-circular">Circular</button>
                <button onclick="updateLayout('force_directed')" id="btn-force_directed">Force Directed</button>
            </div>

            <div class="control-group">
                <h3>View Options</h3>
                <button onclick="toggleTools()" id="btn-tools">Hide Tools</button>
                <button onclick="fitView()">Fit to View</button>
                <button onclick="resetZoom()">Reset Zoom</button>
            </div>

            <div class="stats">
                <h4>Agency Statistics</h4>
                <div id="stats-agents">Agents: 0</div>
                <div id="stats-tools">Tools: 0</div>
                <div id="stats-flows">Communication Flows: 0</div>
            </div>
        </div>

        <div class="visualization-wrapper">
            <svg id="visualization-svg" viewBox="0 0 800 600">
                <!-- Gradients for nodes -->
                <defs>
                    <linearGradient id="agentGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
                    </linearGradient>
                    <linearGradient id="toolGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#ffeaa7;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#fab1a0;stop-opacity:1" />
                    </linearGradient>
                    <linearGradient id="entryGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#00b894;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#00cec9;stop-opacity:1" />
                    </linearGradient>
                    <marker id="arrowhead" markerWidth="10" markerHeight="7"
                            refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#667eea" />
                    </marker>
                </defs>

                <!-- Edges will be drawn here -->
                <g id="edges-group"></g>

                <!-- Nodes will be drawn here -->
                <g id="nodes-group"></g>
            </svg>

            <div class="zoom-controls">
                <button class="zoom-btn" onclick="zoomIn()">+</button>
                <button class="zoom-btn" onclick="zoomOut()">−</button>
                <button class="zoom-btn" onclick="resetZoom()" title="Reset Zoom">⌂</button>
            </div>
        </div>
    </div>

    <script>
        // Agency data embedded from Python
        const agencyData = {agency_json};

        // Debug: Log the data structure
        console.log('🔍 Agency Data:', agencyData);
        console.log('📊 Nodes:', agencyData.nodes?.length || 0);
        console.log('🔗 Edges:', agencyData.edges?.length || 0);

        // Visualization state
        let showTools = true;
        let currentZoom = 1;
        let panX = 0;
        let panY = 0;
        let isDragging = false;
        let dragStart = {{ x: 0, y: 0 }};
        let draggedNode = null;
        let nodePositions = new Map();

        // SVG elements
        const svg = document.getElementById('visualization-svg');
        const nodesGroup = document.getElementById('nodes-group');
        const edgesGroup = document.getElementById('edges-group');

        // Text wrapping utility
        function wrapText(text, maxCharsPerLine) {{
            if (text.length <= maxCharsPerLine) {{
                return [text];
            }}

            const lines = [];
            let currentLine = '';
            const words = text.split(/([_\\s-])/); // Split on underscores, spaces, and hyphens but keep delimiters

            for (let i = 0; i < words.length; i++) {{
                const word = words[i];
                const testLine = currentLine + word;

                if (testLine.length <= maxCharsPerLine) {{
                    currentLine = testLine;
                }} else {{
                    if (currentLine.length > 0) {{
                        lines.push(currentLine);
                        currentLine = word;
                    }} else {{
                        // Word is longer than max chars, force break
                        lines.push(word.substring(0, maxCharsPerLine));
                        currentLine = word.substring(maxCharsPerLine);
                    }}
                }}
            }}

            if (currentLine.length > 0) {{
                lines.push(currentLine);
            }}

            return lines;
        }}

        // Initialize visualization
        function initVisualization() {{
            console.log('✅ Initializing SVG visualization...');

            // Update stats
            updateStats();

            // Draw the visualization
            drawVisualization();

            // Add pan/zoom functionality
            addPanZoomHandlers();

            console.log('✅ SVG visualization initialized successfully');
        }}

        function drawVisualization() {{
            // Clear existing content
            nodesGroup.innerHTML = '';
            edgesGroup.innerHTML = '';

            // Initialize node positions if not already done
            if (nodePositions.size === 0) {{
                agencyData.nodes.forEach(node => {{
                    nodePositions.set(node.id, {{ x: node.position.x, y: node.position.y }});
                }});
            }}

            const nodes = showTools ? agencyData.nodes : agencyData.nodes.filter(n => n.type === 'agent');
            const edges = showTools ? agencyData.edges : agencyData.edges.filter(e => {{
                const sourceNode = agencyData.nodes.find(n => n.id === e.source);
                const targetNode = agencyData.nodes.find(n => n.id === e.target);
                return sourceNode?.type === 'agent' && targetNode?.type === 'agent';
            }});

            // Draw edges first (so they appear behind nodes)
            edges.forEach(edge => {{
                const sourceNode = agencyData.nodes.find(n => n.id === edge.source);
                const targetNode = agencyData.nodes.find(n => n.id === edge.target);

                if (sourceNode && targetNode) {{
                    drawEdge(sourceNode, targetNode, edge);
                }}
            }});

            // Draw nodes
            nodes.forEach(node => {{
                drawNode(node);
            }});
        }}

        function drawNode(node) {{
            // Get current position (may have been updated by dragging)
            const currentPos = nodePositions.get(node.id) || node.position;
            const x = currentPos.x;
            const y = currentPos.y;
            const isAgent = node.type === 'agent';
            const isEntryPoint = node.data?.isEntryPoint;

            // Create node group
            const nodeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            nodeGroup.setAttribute('transform', `translate(${{x}}, ${{y}})`);
            nodeGroup.setAttribute('data-node-id', node.id);
            nodeGroup.style.cursor = 'move';

            // Create rectangle
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('width', isAgent ? '120' : '100');
            rect.setAttribute('height', isAgent ? '60' : '50');
            rect.setAttribute('rx', isAgent ? '10' : '8');
            rect.setAttribute('ry', isAgent ? '10' : '8');
            rect.setAttribute('x', isAgent ? '-60' : '-50');
            rect.setAttribute('y', isAgent ? '-30' : '-25');

            if (isAgent) {{
                rect.setAttribute('class', isEntryPoint ? 'node-entry-point' : 'node-agent');
            }} else {{
                rect.setAttribute('class', 'node-tool');
            }}

            // Create wrapped text
            const displayText = node.data?.label || node.id;
            const maxCharsPerLine = isAgent ? 16 : 14;
            const textLines = wrapText(displayText, maxCharsPerLine);

            // Calculate dynamic node height based on text lines
            const baseHeight = isAgent ? 60 : 50;
            const lineHeight = 12;
            const extraHeight = Math.max(0, (textLines.length - 1) * lineHeight);
            const nodeHeight = baseHeight + extraHeight;

            // Update rectangle height
            rect.setAttribute('height', nodeHeight.toString());
            rect.setAttribute('y', (-nodeHeight / 2).toString());

            // Create text group for multiple lines
            const textGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');

            // Calculate starting Y position to center text vertically
            const totalTextHeight = textLines.length * lineHeight;
            const startY = -totalTextHeight / 2 + lineHeight / 2;

            textLines.forEach((line, i) => {{
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', '0');
                text.setAttribute('y', startY + (i * lineHeight));
                text.setAttribute('class', isAgent ? 'node-text' : 'node-text node-text-tool');
                text.setAttribute('font-size', isAgent ? '12' : '10');
                text.textContent = line;
                textGroup.appendChild(text);
            }});

            // Create description text (only for agents, simplified)
            if (node.data?.description && isAgent && textLines.length <= 2) {{
                const desc = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                desc.setAttribute('x', '0');
                desc.setAttribute('y', (nodeHeight / 2) - 8);
                desc.setAttribute('class', 'node-text');
                desc.setAttribute('font-size', '9');
                desc.setAttribute('opacity', '0.7');
                desc.textContent = node.data.description.length > 12 ?
                    node.data.description.substring(0, 12) + '...' :
                    node.data.description;
                nodeGroup.appendChild(desc);
            }}

            nodeGroup.appendChild(rect);
            nodeGroup.appendChild(textGroup);

            // Add node-specific drag handlers
            nodeGroup.addEventListener('mousedown', (e) => {{
                e.stopPropagation(); // Prevent canvas panning
                startNodeDrag(e, node);
            }});

            // Add click handler (only if not dragging)
            nodeGroup.addEventListener('click', (e) => {{
                if (!isDragging) {{
                    console.log('Node clicked:', node);
                }}
            }});

            nodesGroup.appendChild(nodeGroup);
        }}

        function drawEdge(sourceNode, targetNode, edge) {{
            // Get current positions (may have been updated by dragging)
            const sourcePos = nodePositions.get(sourceNode.id) || sourceNode.position;
            const targetPos = nodePositions.get(targetNode.id) || targetNode.position;
            const x1 = sourcePos.x;
            const y1 = sourcePos.y;
            const x2 = targetPos.x;
            const y2 = targetPos.y;

            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');

            // Create a simple curved path
            const midX = (x1 + x2) / 2;
            const midY = (y1 + y2) / 2;
            const controlX = midX;
            const controlY = midY - 30;

            const pathData = `M ${{x1}} ${{y1}} Q ${{controlX}} ${{controlY}} ${{x2}} ${{y2}}`;
            path.setAttribute('d', pathData);

            const isToolEdge = edge.type === 'tool' ||
                              sourceNode.type === 'tool' ||
                              targetNode.type === 'tool';

            path.setAttribute('class', isToolEdge ? 'edge edge-tool' : 'edge');

            edgesGroup.appendChild(path);
        }}

        function addPanZoomHandlers() {{
            svg.addEventListener('mousedown', startCanvasDrag);
            svg.addEventListener('mousemove', handleMouseMove);
            svg.addEventListener('mouseup', endDrag);
            svg.addEventListener('mouseleave', endDrag);
            svg.addEventListener('wheel', zoom);
        }}

        function startCanvasDrag(e) {{
            // Only start canvas drag if not clicking on a node
            if (e.target.closest('[data-node-id]')) return;

            isDragging = true;
            draggedNode = null;
            dragStart.x = e.clientX - panX;
            dragStart.y = e.clientY - panY;
        }}

        function startNodeDrag(e, node) {{
            isDragging = true;
            draggedNode = node;

            // Get mouse position in SVG coordinates
            const rect = svg.getBoundingClientRect();
            const svgX = (e.clientX - rect.left - panX) / currentZoom;
            const svgY = (e.clientY - rect.top - panY) / currentZoom;

            const currentPos = nodePositions.get(node.id);
            dragStart.x = svgX - currentPos.x;
            dragStart.y = svgY - currentPos.y;
        }}

        function handleMouseMove(e) {{
            if (!isDragging) return;

            if (draggedNode) {{
                // Node dragging
                const rect = svg.getBoundingClientRect();
                const svgX = (e.clientX - rect.left - panX) / currentZoom;
                const svgY = (e.clientY - rect.top - panY) / currentZoom;

                const newX = svgX - dragStart.x;
                const newY = svgY - dragStart.y;

                // Update node position
                nodePositions.set(draggedNode.id, {{ x: newX, y: newY }});

                // Redraw visualization
                drawVisualization();
            }} else {{
                // Canvas panning
                panX = e.clientX - dragStart.x;
                panY = e.clientY - dragStart.y;
                updateTransform();
            }}
        }}

        function endDrag() {{
            isDragging = false;
            draggedNode = null;
        }}

        function zoom(e) {{
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            currentZoom *= delta;
            currentZoom = Math.max(0.1, Math.min(3, currentZoom));
            updateTransform();
        }}

        function updateTransform() {{
            const transform = `translate(${{panX}}, ${{panY}}) scale(${{currentZoom}})`;
            nodesGroup.setAttribute('transform', transform);
            edgesGroup.setAttribute('transform', transform);
        }}

        // Layout algorithms
        function applyHierarchicalLayout() {{
            const agents = agencyData.nodes.filter(n => n.type === 'agent');
            const tools = agencyData.nodes.filter(n => n.type === 'tool');

            // Position agents in a hierarchy
            agents.forEach((agent, i) => {{
                const x = 100 + (i % 2) * 300;
                const y = 50 + Math.floor(i / 2) * 200;
                nodePositions.set(agent.id, {{ x, y }});
            }});

            // Position tools around their agents
            tools.forEach((tool, i) => {{
                const x = 50 + (i % 4) * 150;
                const y = 300 + Math.floor(i / 4) * 100;
                nodePositions.set(tool.id, {{ x, y }});
            }});
        }}

        function applyCircularLayout() {{
            const allNodes = agencyData.nodes;
            const centerX = 400;
            const centerY = 300;
            const radius = 150;

            allNodes.forEach((node, i) => {{
                const angle = (i / allNodes.length) * 2 * Math.PI;
                const x = centerX + radius * Math.cos(angle);
                const y = centerY + radius * Math.sin(angle);
                nodePositions.set(node.id, {{ x, y }});
            }});
        }}

        function applyForceDirectedLayout() {{
            const agents = agencyData.nodes.filter(n => n.type === 'agent');
            const tools = agencyData.nodes.filter(n => n.type === 'tool');

            // Spread agents across the canvas
            agents.forEach((agent, i) => {{
                const x = 100 + Math.random() * 600;
                const y = 100 + Math.random() * 400;
                nodePositions.set(agent.id, {{ x, y }});
            }});

            // Position tools randomly but clustered
            tools.forEach((tool, i) => {{
                const x = 200 + Math.random() * 400;
                const y = 200 + Math.random() * 200;
                nodePositions.set(tool.id, {{ x, y }});
            }});
        }}

        // Control functions
        function updateLayout(layoutType) {{
            // Update active button
            document.querySelectorAll('.control-group button').forEach(btn => btn.classList.remove('active'));
            document.getElementById(`btn-${{layoutType}}`).classList.add('active');

            // Apply the selected layout
            switch(layoutType) {{
                case 'hierarchical':
                    applyHierarchicalLayout();
                    break;
                case 'circular':
                    applyCircularLayout();
                    break;
                case 'force_directed':
                    applyForceDirectedLayout();
                    break;
            }}

            // Redraw with new positions
            drawVisualization();

            console.log(`Applied ${{layoutType}} layout`);
        }}

        function toggleTools() {{
            showTools = !showTools;
            const btn = document.getElementById('btn-tools');
            btn.textContent = showTools ? 'Hide Tools' : 'Show Tools';

            drawVisualization();
            updateStats();

            console.log(`Tools ${{showTools ? 'shown' : 'hidden'}}`);
        }}

        function fitView() {{
            currentZoom = 1;
            panX = 0;
            panY = 0;
            updateTransform();
        }}

        function resetZoom() {{
            currentZoom = 1;
            panX = 0;
            panY = 0;
            updateTransform();
        }}

        function zoomIn() {{
            currentZoom *= 1.2;
            currentZoom = Math.min(3, currentZoom);
            updateTransform();
        }}

        function zoomOut() {{
            currentZoom *= 0.8;
            currentZoom = Math.max(0.1, currentZoom);
            updateTransform();
        }}

        function updateStats() {{
            const visibleNodes = showTools ? agencyData.nodes : agencyData.nodes.filter(n => n.type === 'agent');
            const agents = visibleNodes.filter(n => n.type === 'agent').length;
            const tools = visibleNodes.filter(n => n.type === 'tool').length;
            const flows = agencyData.edges.length;

            document.getElementById('stats-agents').textContent = `Agents: ${{agents}}`;
            document.getElementById('stats-tools').textContent = `Tools: ${{tools}}`;
            document.getElementById('stats-flows').textContent = `Communication Flows: ${{flows}}`;
        }}

        // Initialize when page loads
        document.addEventListener('DOMContentLoaded', initVisualization);
    </script>
</body>
</html>"""

    # Write the HTML file
    with open(output_file, "w") as f:
        f.write(html_template)

    return output_file


def main():
    """Generate ReactFlow integration example"""
    print("🔄 Generating ReactFlow Integration Example")
    print("=" * 50)

    # Create demo agency
    print("Creating software development agency...")
    agency = create_demo_agency()

    # Get agency structure data (all logic is in agency.py)
    print("Generating agency structure data...")
    try:
        agency_data = agency.get_agency_structure(layout_algorithm="hierarchical", include_tools=True)

        # Generate interactive HTML (minimal - just visualization)
        print("Creating interactive HTML visualization...")
        html_file = generate_reactflow_html(agency_data)

        # Get file size
        file_size = os.path.getsize(html_file)

        print(f"✅ Generated: {html_file} ({file_size:,} bytes)")
        print()
        print("🌐 Opening interactive visualization in your default browser...")

        # Automatically open the HTML file in the default browser
        file_path = os.path.abspath(html_file)
        webbrowser.open(f"file://{file_path}")

        print("✅ Browser opened! You should see the interactive visualization.")
        print()
        print("Features included:")
        print("  - Interactive node dragging and zooming")
        print("  - Multiple layout algorithms")
        print("  - Tool visibility toggle")
        print("  - Communication flow arrows")
        print("  - Real-time statistics")

        # Show structure summary (minimal)
        metadata = agency_data.get("metadata", {})
        print()
        print("Agency Structure:")
        print(f"  - Agents: {metadata.get('totalAgents', 0)}")
        print(f"  - Tools: {metadata.get('totalTools', 0)}")
        print(f"  - Entry Points: {', '.join(metadata.get('entryPoints', []))}")

    except Exception as e:
        print(f"❌ Error generating ReactFlow example: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
