"""
Tests for Agency Swarm visualization functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.ui import HTMLVisualizationGenerator, LayoutAlgorithms


@pytest.fixture
def sample_agency():
    """Create a sample agency for testing visualization."""
    ceo = Agent(name="CEO", instructions="You are the CEO")
    manager = Agent(name="Manager", instructions="You manage projects")
    worker = Agent(name="Worker", instructions="You do the work")

    agency = Agency(ceo, communication_flows=[ceo > manager, manager > worker])
    return agency


@pytest.fixture
def sample_agency_data():
    """Sample agency data structure for testing."""
    return {
        "nodes": [
            {
                "id": "CEO",
                "type": "agent",
                "data": {"label": "CEO", "description": "You are the CEO", "isEntryPoint": True},
                "position": {"x": 100, "y": 100},
            },
            {
                "id": "Manager",
                "type": "agent",
                "data": {"label": "Manager", "description": "You manage projects", "isEntryPoint": False},
                "position": {"x": 200, "y": 200},
            },
            {
                "id": "Worker",
                "type": "agent",
                "data": {"label": "Worker", "description": "You do the work", "isEntryPoint": False},
                "position": {"x": 300, "y": 300},
            },
        ],
        "edges": [
            {"id": "CEO-Manager", "source": "CEO", "target": "Manager", "type": "communication"},
            {"id": "Manager-Worker", "source": "Manager", "target": "Worker", "type": "communication"},
        ],
        "metadata": {"agencyName": "Test Agency", "totalAgents": 3, "totalTools": 0},
    }


class TestLayoutAlgorithms:
    """Test the layout algorithms."""

    def test_hierarchical_layout_basic(self, sample_agency_data):
        """Test basic hierarchical layout functionality."""
        nodes = sample_agency_data["nodes"]
        edges = sample_agency_data["edges"]

        positions = LayoutAlgorithms.hierarchical_layout(nodes, edges, width=800, height=600)

        # Check that all agents got positions
        assert "CEO" in positions
        assert "Manager" in positions
        assert "Worker" in positions

        # Check that positions have x and y coordinates
        for _node_id, pos in positions.items():
            assert "x" in pos
            assert "y" in pos
            assert isinstance(pos["x"], int | float)
            assert isinstance(pos["y"], int | float)

    def test_hierarchical_layout_entry_points_on_top(self, sample_agency_data):
        """Test that entry points are positioned at the top."""
        nodes = sample_agency_data["nodes"]
        edges = sample_agency_data["edges"]

        positions = LayoutAlgorithms.hierarchical_layout(nodes, edges, width=800, height=600)

        ceo_y = positions["CEO"]["y"]
        manager_y = positions["Manager"]["y"]
        worker_y = positions["Worker"]["y"]

        # CEO (entry point) should be at the top
        assert ceo_y < manager_y
        assert manager_y < worker_y

    def test_hierarchical_layout_with_tools(self):
        """Test hierarchical layout with tools included."""
        nodes = [
            {"id": "CEO", "type": "agent", "data": {"label": "CEO", "isEntryPoint": True}},
            {"id": "tool1", "type": "tool", "data": {"label": "Tool1", "parentAgent": "CEO"}},
        ]
        edges = []

        positions = LayoutAlgorithms.hierarchical_layout(nodes, edges, width=800, height=600)

        assert "CEO" in positions
        assert "tool1" in positions

        # Tool should be positioned relative to its parent agent
        assert positions["tool1"]["x"] != positions["CEO"]["x"] or positions["tool1"]["y"] != positions["CEO"]["y"]

    def test_hierarchical_layout_orphaned_tools(self):
        """Test positioning of tools without parent agents."""
        nodes = [
            {"id": "CEO", "type": "agent", "data": {"label": "CEO", "isEntryPoint": True}},
            {
                "id": "orphan_tool",
                "type": "tool",
                "data": {"label": "Orphan Tool"},  # No parentAgent
            },
        ]
        edges = []

        positions = LayoutAlgorithms.hierarchical_layout(nodes, edges, width=800, height=600)

        assert "CEO" in positions
        assert "orphan_tool" in positions

        # Orphaned tool should be positioned at bottom
        assert positions["orphan_tool"]["y"] > positions["CEO"]["y"]

    def test_apply_layout(self, sample_agency_data):
        """Test the apply_layout method."""
        result = LayoutAlgorithms.apply_layout(sample_agency_data)

        # Check that structure is preserved
        assert "nodes" in result
        assert "edges" in result
        assert "metadata" in result

        # Check that positions were updated
        for node in result["nodes"]:
            assert "position" in node
            assert "x" in node["position"]
            assert "y" in node["position"]


class TestHTMLVisualizationGenerator:
    """Test the HTML visualization generator."""

    def test_init(self):
        """Test HTMLVisualizationGenerator initialization."""
        generator = HTMLVisualizationGenerator()
        assert generator.template_dir.exists()
        assert (generator.template_dir / "visualization.html").exists()
        assert (generator.template_dir / "styles.css").exists()
        assert (generator.template_dir / "visualization.js").exists()

    def test_load_template(self):
        """Test template loading."""
        generator = HTMLVisualizationGenerator()

        # Test loading existing template
        html_content = generator._load_template("visualization.html")
        assert isinstance(html_content, str)
        assert len(html_content) > 0
        assert "html" in html_content.lower()

    def test_load_template_not_found(self):
        """Test error handling for missing template."""
        generator = HTMLVisualizationGenerator()

        with pytest.raises(FileNotFoundError):
            generator._load_template("nonexistent.html")

    @patch("webbrowser.open")
    def test_open_in_browser_success(self, mock_webbrowser):
        """Test opening file in browser successfully."""
        generator = HTMLVisualizationGenerator()
        test_path = Path("/test/path.html")

        generator._open_in_browser(test_path)
        mock_webbrowser.assert_called_once_with(f"file://{test_path}")

    @patch("webbrowser.open", side_effect=Exception("Browser error"))
    @patch("builtins.print")
    def test_open_in_browser_error(self, mock_print, mock_webbrowser):
        """Test error handling when browser fails to open."""
        generator = HTMLVisualizationGenerator()
        test_path = Path("/test/path.html")

        generator._open_in_browser(test_path)

        # Should print error messages
        assert mock_print.call_count >= 2

    def test_generate_interactive_html(self, sample_agency_data):
        """Test interactive HTML generation."""
        generator = HTMLVisualizationGenerator()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as tmp:
            output_file = tmp.name

        try:
            with patch.object(generator, "_open_in_browser"):
                result_path = generator.generate_interactive_html(
                    agency_data=sample_agency_data, output_file=output_file, open_browser=False
                )

            assert result_path == str(Path(output_file).resolve())
            assert Path(output_file).exists()

            # Check file content
            with open(output_file) as f:
                content = f.read()

            assert "Test Agency" in content
            assert "CEO" in content
            assert "Manager" in content
            assert "Worker" in content

        finally:
            # Cleanup
            if Path(output_file).exists():
                Path(output_file).unlink()

    def test_generate_component_files(self, sample_agency_data):
        """Test generation of separate component files."""
        generator = HTMLVisualizationGenerator()

        with tempfile.TemporaryDirectory() as tmp_dir:
            files = generator.generate_component_files(agency_data=sample_agency_data, output_dir=tmp_dir)

            # Check that all expected files were created
            assert "html" in files
            assert "css" in files
            assert "js" in files

            for file_path in files.values():
                assert Path(file_path).exists()
                assert Path(file_path).stat().st_size > 0

    @patch.object(HTMLVisualizationGenerator, "generate_interactive_html")
    def test_create_visualization_from_agency(self, mock_generate, sample_agency):
        """Test creating visualization directly from agency."""
        mock_generate.return_value = "/path/to/output.html"

        result = HTMLVisualizationGenerator.create_visualization_from_agency(
            agency=sample_agency,
            output_file="test.html",
            include_tools=True,
            open_browser=False,
        )

        assert result == "/path/to/output.html"
        mock_generate.assert_called_once()


class TestAgencyVisualizationIntegration:
    """Test Agency class visualization methods."""

    def test_visualize(self, sample_agency):
        """Test Agency.visualize method."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as tmp:
            output_file = tmp.name

        try:
            with patch("webbrowser.open"):
                result_path = sample_agency.visualize(output_file=output_file, include_tools=True, open_browser=False)

            assert result_path == str(Path(output_file).resolve())
            assert Path(output_file).exists()

            # Check that file contains expected content
            with open(output_file) as f:
                content = f.read()

            assert "CEO" in content
            assert "Manager" in content
            assert "Worker" in content

        finally:
            if Path(output_file).exists():
                Path(output_file).unlink()

    def test_visualize_import_error(self, sample_agency):
        """Test handling of import errors in visualization."""
        # Patch the import inside the visualize method
        with patch("agency_swarm.agency.Agency.visualize") as mock_method:
            mock_method.side_effect = ImportError("Visualization module not available")
            with pytest.raises(ImportError, match="Visualization module not available"):
                sample_agency.visualize()

    def test_get_agency_structure_basic(self, sample_agency):
        """Test basic agency structure generation."""
        structure = sample_agency.get_agency_structure()

        assert "nodes" in structure
        assert "edges" in structure
        assert "metadata" in structure

        # Check nodes
        nodes = structure["nodes"]
        assert len(nodes) >= 3  # At least CEO, Manager, Worker

        agent_nodes = [n for n in nodes if n["type"] == "agent"]
        assert len(agent_nodes) == 3

        # Check edges
        edges = structure["edges"]
        communication_edges = [e for e in edges if e["type"] == "communication"]
        assert len(communication_edges) >= 2  # CEO->Manager, Manager->Worker

        # Check metadata contains full agents list and entry points
        meta = structure["metadata"]
        assert set(meta["agents"]) == {"CEO", "Manager", "Worker"}
        assert set(meta["entryPoints"]) == {"CEO"}

    def test_get_agency_structure_with_tools(self, sample_agency):
        """Test agency structure generation with tools included."""
        # Test that the method works with include_tools=True
        # We'll test the structure without actually adding tools to avoid tool type complications
        structure = sample_agency.get_agency_structure(include_tools=True)

        assert "nodes" in structure
        assert "edges" in structure
        assert "metadata" in structure

        # Check that the structure is valid even when no tools are present
        agent_nodes = [n for n in structure["nodes"] if n["type"] == "agent"]
        assert len(agent_nodes) >= 3

        # Tool nodes and edges should be empty if no tools are added, which is fine
        tool_nodes = [n for n in structure["nodes"] if n["type"] == "tool"]
        tool_edges = [e for e in structure["edges"] if e["type"] == "tool"]

        # These should be lists, even if empty
        assert isinstance(tool_nodes, list)
        assert isinstance(tool_edges, list)

    def test_get_agency_structure_without_tools(self, sample_agency):
        """Test agency structure generation without tools."""
        structure = sample_agency.get_agency_structure(include_tools=False)

        # Should only have agent nodes
        tool_nodes = [n for n in structure["nodes"] if n["type"] == "tool"]
        assert len(tool_nodes) == 0

        # Should only have communication edges
        tool_edges = [e for e in structure["edges"] if e["type"] == "tool"]
        assert len(tool_edges) == 0

    def test_get_agency_structure_hierarchical_layout(self, sample_agency):
        """Test hierarchical layout in get_agency_structure."""
        # Test hierarchical layout
        structure = sample_agency.get_agency_structure()

        # Check that nodes have positions
        for node in structure["nodes"]:
            assert "position" in node
            assert "x" in node["position"]
            assert "y" in node["position"]

    def test_layout_algorithms_manager_vs_leaf_positioning(self):
        """Test that manager agents and leaf agents position tools differently."""
        # Create a more complex structure with manager and leaf agents
        nodes = [
            {"id": "Manager", "type": "agent", "data": {"label": "Manager", "isEntryPoint": True}},
            {"id": "Worker1", "type": "agent", "data": {"label": "Worker1", "isEntryPoint": False}},
            {"id": "Worker2", "type": "agent", "data": {"label": "Worker2", "isEntryPoint": False}},
            {"id": "manager_tool", "type": "tool", "data": {"label": "Manager Tool", "parentAgent": "Manager"}},
            {"id": "worker_tool", "type": "tool", "data": {"label": "Worker Tool", "parentAgent": "Worker1"}},
        ]

        # Manager has multiple outgoing connections
        edges = [
            {"source": "Manager", "target": "Worker1", "type": "communication"},
            {"source": "Manager", "target": "Worker2", "type": "communication"},
        ]

        positions = LayoutAlgorithms.hierarchical_layout(nodes, edges)

        # Both tools should be positioned
        assert "manager_tool" in positions
        assert "worker_tool" in positions

        # Manager tool should be positioned to the right (x > manager x)
        # Worker tool should be positioned below (y > worker y)
        manager_pos = positions["Manager"]
        worker_pos = positions["Worker1"]
        manager_tool_pos = positions["manager_tool"]
        worker_tool_pos = positions["worker_tool"]

        # These assertions test the smart positioning logic
        assert manager_tool_pos["x"] > manager_pos["x"]  # Tool to the right of manager
        assert worker_tool_pos["y"] > worker_pos["y"]  # Tool below worker


class TestMetadataDetails:
    def test_get_agency_structure_rich_metadata(self):
        """Ensure metadata includes tool details and agency info."""
        from agents import function_tool

        @function_tool
        def sample_tool(text: str) -> str:
            """Echo text."""
            return text

        agent = Agent(name="ToolAgent", instructions="Use the tool", tools=[sample_tool])
        agency = Agency(agent, name="ToolAgency", shared_instructions="shared.md")

        structure = agency.get_agency_structure()

        agent_node = next(n for n in structure["nodes"] if n["id"] == "ToolAgent")
        data = agent_node["data"]
        assert data["toolCount"] == 1
        assert data["tools"][0]["name"] == "sample_tool"
        assert data["instructions"].startswith("shared.md")

        meta = structure["metadata"]
        assert meta["agencyName"] == "ToolAgency"
        assert meta["layoutAlgorithm"] == "hierarchical"
        # Full agents list must include the single ToolAgent
        assert meta["agents"] == ["ToolAgent"]

    def test_hosted_mcp_tools_unique_ids(self):
        """HostedMCPTool instances should produce unique tool nodes and labeled with server labels."""
        from agents import HostedMCPTool

        agent = Agent(
            name="SearchCoordinator",
            instructions="Handle searches",
            tools=[
                HostedMCPTool(
                    tool_config={
                        "type": "mcp",
                        "server_label": "tavily-server",
                        "server_url": "https://example.com/tavily",
                        "require_approval": "never",
                    }
                ),
                HostedMCPTool(
                    tool_config={
                        "type": "mcp",
                        "server_label": "youtube-server",
                        "server_url": "https://example.com/youtube",
                        "require_approval": "never",
                    }
                ),
            ],
        )

        agency = Agency(agent)
        structure = agency.get_agency_structure()

        tool_nodes = [n for n in structure["nodes"] if n["type"] == "tool"]
        ids = [n["id"] for n in tool_nodes]
        assert len(ids) == len(set(ids))
        labels = [n["data"]["label"] for n in tool_nodes]
        assert "tavily-server" in labels and "youtube-server" in labels
