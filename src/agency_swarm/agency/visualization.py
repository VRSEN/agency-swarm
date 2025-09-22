# --- Agency visualization and demo methods ---
import logging
from typing import TYPE_CHECKING, Any

from agency_swarm.ui.demos.copilot import CopilotDemoLauncher
from agency_swarm.ui.demos.terminal import start_terminal
from agency_swarm.ui.generators.html_generator import HTMLVisualizationGenerator

if TYPE_CHECKING:
    from .core import Agency

logger = logging.getLogger(__name__)


def get_agency_structure(agency: "Agency", include_tools: bool = True) -> dict[str, Any]:
    """Return a ReactFlow-compatible JSON structure describing the agency."""
    from agency_swarm.ui.core.layout_algorithms import LayoutAlgorithms

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Create agent nodes
    for agent_name, agent in agency.agents.items():
        is_entry_point = agent in agency.entry_points

        # Combine shared and agent-specific instructions
        if agency.shared_instructions and getattr(agent, "instructions", None):
            instructions = f"{agency.shared_instructions}\n\n---\n\n{agent.instructions}"
        else:
            instructions = agency.shared_instructions or getattr(agent, "instructions", "") or ""

        agent_data: dict[str, Any] = {
            "label": agent_name,
            "description": getattr(agent, "description", "") or "",
            "isEntryPoint": is_entry_point,
            "toolCount": 0,
            "tools": [],
            "instructions": instructions,
            "model": agent.model,
            "hasSubagents": bool(getattr(agent, "_subagents", {})),
        }

        node = {
            "id": agent_name,
            "data": agent_data,
            "type": "agent",
            "position": {"x": 0, "y": 0},
        }

        # Add tools if requested
        if include_tools and agent.tools:
            for idx, tool in enumerate(agent.tools):
                tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))

                # Skip send_message tools in visualization
                if tool_name.startswith("send_message"):
                    continue

                tool_type = getattr(tool, "type", tool.__class__.__name__)
                tool_desc = getattr(tool, "description", getattr(tool, "__doc__", "")) or ""

                # Handle Hosted MCP tools with server labels for uniqueness/clarity
                if tool_name == "hosted_mcp":
                    tool_config = getattr(tool, "tool_config", {})
                    server_label = tool_config.get("server_label") if isinstance(tool_config, dict) else None
                    display_name = server_label or tool_name
                else:
                    display_name = tool_name

                agent_data["tools"].append({"name": display_name, "type": tool_type, "description": tool_desc})
                agent_data["toolCount"] += 1

                tool_node = {
                    "id": f"{agent_name}_tool_{idx}",
                    "data": {
                        "label": display_name,
                        "description": tool_desc,
                        "type": tool_type,
                        "parentAgent": agent_name,
                    },
                    "type": "tool",
                    "position": {"x": 0, "y": 0},
                }
                nodes.append(tool_node)

                tool_edge = {
                    "id": f"{agent_name}->{agent_name}_tool_{idx}",
                    "source": agent_name,
                    "target": f"{agent_name}_tool_{idx}",
                    "type": "owns",
                }
                edges.append(tool_edge)

        nodes.append(node)

    # Create communication edges from flows
    for sender, receiver in agency._derived_communication_flows:
        edges.append(
            {
                "id": f"{sender.name}->{receiver.name}",
                "source": sender.name,
                "target": receiver.name,
                "type": "communication",
                "data": {"label": "can send messages to", "bidirectional": False},
            }
        )

    # Create metadata
    metadata = {
        "agencyName": getattr(agency, "name", None) or "Unnamed Agency",
        "totalAgents": len(agency.agents),
        "totalTools": sum(len(a.tools) if a.tools else 0 for a in agency.agents.values()),
        "agents": list(agency.agents.keys()),
        "entryPoints": [ep.name for ep in agency.entry_points],
        "sharedInstructions": agency.shared_instructions or "",
        "layoutAlgorithm": "hierarchical",
    }

    agency_data = {"nodes": nodes, "edges": edges, "metadata": metadata}

    layout = LayoutAlgorithms()
    return layout.apply_layout(agency_data)


def visualize(
    agency: "Agency",
    output_file: str = "agency_visualization.html",
    include_tools: bool = True,
    open_browser: bool = True,
) -> str:
    """
    Create a visual representation of the agency structure.

    Args:
        output_file: Path to save the HTML file
        include_tools: Whether to include agent tools as separate nodes
        open_browser: Whether to open the file in a browser

    Returns:
        Path to the generated file
    """
    return HTMLVisualizationGenerator.create_visualization_from_agency(
        agency=agency,
        output_file=output_file,
        include_tools=include_tools,
        open_browser=open_browser,
    )


def terminal_demo(agency: "Agency", show_reasoning: bool = False) -> None:
    """
    Run a terminal demo of the agency.
    """
    # Call terminal demo entry directly
    start_terminal(agency, show_reasoning=show_reasoning)


def copilot_demo(
    agency: "Agency",
    host: str = "0.0.0.0",
    port: int = 8000,
    frontend_port: int = 3000,
    cors_origins: list[str] | None = None,
) -> None:
    """
    Run a copilot demo of the agency.
    """
    CopilotDemoLauncher.start(agency, host=host, port=port, frontend_port=frontend_port, cors_origins=cors_origins)
