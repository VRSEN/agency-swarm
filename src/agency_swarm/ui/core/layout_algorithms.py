"""
Layout algorithms for agency visualization.
"""

from typing import Any


class LayoutAlgorithms:
    """
    Layout algorithms for positioning nodes in agency visualizations.
    """

    @staticmethod
    def hierarchical_layout(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]], width: int = 800, height: int = 600
    ) -> dict[str, dict[str, float]]:
        """
        Create a hierarchical layout.
        Entry points at top, subsequent layers below.
        """
        positions: dict[str, dict[str, float]] = {}

        # Node sizing constants
        AGENT_WIDTH = 120
        AGENT_HEIGHT = 60
        TOOL_WIDTH = 100
        TOOL_HEIGHT = 50
        MIN_SPACING_X = 120  # Minimum horizontal spacing between nodes (doubled for clear separation)
        MIN_SPACING_Y = 120  # Minimum vertical spacing between layers (increased)

        # Identify entry points and regular agents
        entry_points = [node for node in nodes if node.get("data", {}).get("isEntryPoint", False)]
        agents = [node for node in nodes if node["type"] == "agent"]
        tools = [node for node in nodes if node["type"] == "tool"]

        # Build adjacency graph for flow analysis
        graph: dict[str, list[str]] = {}
        for node in nodes:
            graph[node["id"]] = []

        for edge in edges:
            if edge["type"] == "communication":
                graph[edge["source"]].append(edge["target"])

        # Assign layers using BFS from entry points
        layers: dict[str, int] = {}
        visited: set[str] = set()

        # Start with entry points at layer 0
        for ep in entry_points:
            layers[ep["id"]] = 0
            visited.add(ep["id"])

        # BFS to assign layers
        current_layer = 0
        while True:
            next_layer_nodes: list[str] = []

            for node_id, layer in layers.items():
                if layer == current_layer:
                    for neighbor in graph.get(node_id, []):
                        if neighbor not in visited and any(n["id"] == neighbor and n["type"] == "agent" for n in nodes):
                            next_layer_nodes.append(neighbor)
                            visited.add(neighbor)

            if not next_layer_nodes:
                break

            current_layer += 1
            for node_id in next_layer_nodes:
                layers[node_id] = current_layer

        # Calculate required space for each layer to prevent intersections
        max_layer = max(layers.values()) if layers else 0
        layer_node_counts: dict[int, int] = {}

        for node in agents:
            layer = layers.get(node["id"], max_layer + 1)
            layer_node_counts[layer] = layer_node_counts.get(layer, 0) + 1

        # Position agents layer by layer to ensure consistent spacing
        processed_layers: set[int] = set()
        for node in agents:
            layer = layers.get(node["id"], max_layer + 1)

            # Skip if we've already processed this layer
            if layer in processed_layers:
                continue

            processed_layers.add(layer)
            nodes_in_layer = [n for n in agents if layers.get(n["id"], max_layer + 1) == layer]

            # Calculate total width needed for this layer
            total_nodes = len(nodes_in_layer)
            total_width_needed = (total_nodes * AGENT_WIDTH) + ((total_nodes - 1) * MIN_SPACING_X)

            # Calculate spacing for this layer
            if total_width_needed <= width:
                layer_spacing: float = float(MIN_SPACING_X)
                start_x = (width - total_width_needed) / 2 + (AGENT_WIDTH / 2)
            else:
                # If too wide, compress spacing but maintain minimum
                available_spacing = (width - (total_nodes * AGENT_WIDTH)) / max(total_nodes - 1, 1)
                layer_spacing = float(max(MIN_SPACING_X, available_spacing))
                start_x = AGENT_WIDTH / 2

            # Position all nodes in this layer
            for i, layer_node in enumerate(nodes_in_layer):
                x = start_x + (i * (AGENT_WIDTH + layer_spacing))
                y = 80 + (layer * (AGENT_HEIGHT + MIN_SPACING_Y))
                positions[layer_node["id"]] = {"x": x, "y": y}

        # Position tools based on agent type - smart positioning for better layout
        orphan_count = 0

        # First, identify which agents are managers (have multiple outgoing connections or are intermediate layers)
        agents_with_children: set[str] = set()

        # Count outgoing communication flows for each agent
        outgoing_counts: dict[str, int] = {}
        for edge in edges:
            if edge["type"] == "communication":
                source_agent = edge["source"]
                target_agent = edge["target"]
                if any(n["id"] == source_agent and n["type"] == "agent" for n in nodes) and any(
                    n["id"] == target_agent and n["type"] == "agent" for n in nodes
                ):
                    outgoing_counts[source_agent] = outgoing_counts.get(source_agent, 0) + 1

        # Agents with multiple outgoing connections are managers
        for agent_id, count in outgoing_counts.items():
            if count > 1:
                agents_with_children.add(agent_id)

        # Track tool counts per agent for horizontal spacing
        agent_tool_counts: dict[str, list[dict[str, Any]]] = {}
        for tool in tools:
            parent_agent = tool.get("data", {}).get("parentAgent")
            if parent_agent:
                if parent_agent not in agent_tool_counts:
                    agent_tool_counts[parent_agent] = []
                agent_tool_counts[parent_agent].append(tool)

        for tool in tools:
            parent_agent = tool.get("data", {}).get("parentAgent")
            if parent_agent and parent_agent in positions:
                parent_pos = positions[parent_agent]

                # Get the tools for this agent and find the index
                agent_tools = agent_tool_counts.get(parent_agent, [])
                tool_index = agent_tools.index(tool) if tool in agent_tools else 0
                num_tools = len(agent_tools)

                # Position tools based on parent agent type
                if parent_agent in agents_with_children:
                    # For manager agents (with children): position tools to the right
                    # Spread tools horizontally with consistent spacing
                    tool_spacing = 120  # Consistent with old implementation
                    if num_tools == 1:
                        # Single tool: offset to the right
                        tool_x = parent_pos["x"] + AGENT_WIDTH / 2 + TOOL_WIDTH / 2 + 40
                    else:
                        # Multiple tools: spread horizontally
                        start_x = parent_pos["x"] + AGENT_WIDTH / 2 + TOOL_WIDTH / 2 + 40
                        tool_x = start_x + (tool_index * tool_spacing) - ((num_tools - 1) * tool_spacing / 2)
                    tool_y = parent_pos["y"]
                else:
                    # For leaf agents (no children): position tools below
                    # Use the exact formula from the old implementation
                    tool_spacing = 120
                    # Old formula was: x + (j * 120) - 60
                    # This offsets tools to spread them horizontally
                    tool_x = parent_pos["x"] + (tool_index * tool_spacing) - 60
                    tool_y = parent_pos["y"] + AGENT_HEIGHT / 2 + TOOL_HEIGHT / 2 + 60

                positions[tool["id"]] = {"x": tool_x, "y": tool_y}
            else:
                # Position orphaned tools at the bottom with proper spacing
                orphan_x = 50 + (orphan_count * (TOOL_WIDTH + MIN_SPACING_X))
                orphan_y = height - 80
                positions[tool["id"]] = {"x": orphan_x, "y": orphan_y}
                orphan_count += 1

        return positions

    @staticmethod
    def apply_layout(agency_data: dict[str, Any], width: int = 800, height: int = 600) -> dict[str, Any]:
        """
        Apply hierarchical layout algorithm to agency data and return updated structure.
        """
        nodes = agency_data.get("nodes", [])
        edges = agency_data.get("edges", [])

        # Apply hierarchical layout
        positions = LayoutAlgorithms.hierarchical_layout(nodes, edges, width, height)

        # Update node positions in the data structure
        updated_data = agency_data.copy()
        updated_nodes = []

        for node in nodes:
            updated_node = node.copy()
            if node["id"] in positions:
                updated_node["position"] = positions[node["id"]]
            updated_nodes.append(updated_node)

        updated_data["nodes"] = updated_nodes
        return updated_data
