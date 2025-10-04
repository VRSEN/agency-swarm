"""Tests for create_agent_template utility."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agency_swarm.utils.create_agent_template import create_agent_template


class TestCreateAgentTemplate:
    """Test the create_agent_template function."""

    def test_create_basic_agent_template(self, tmp_path: Path) -> None:
        """Test creating a basic agent template with minimal parameters."""
        agent_name = "Test Agent"

        result = create_agent_template(agent_name=agent_name, path=str(tmp_path))
        assert result is True

        # Check folder structure (now uses underscores)
        agent_folder = tmp_path / "test_agent"
        assert agent_folder.exists()
        assert agent_folder.is_dir()

        # Check required files
        assert (agent_folder / "__init__.py").exists()
        assert (agent_folder / "test_agent.py").exists()
        assert (agent_folder / "instructions.md").exists()

        # Check required directories
        assert (agent_folder / "tools").exists()
        assert (agent_folder / "files").exists()
        assert (agent_folder / "tools" / "__init__.py").exists()
        assert (agent_folder / "tools" / "ExampleTool.py").exists()

    def test_create_agent_template_without_description(self, tmp_path: Path) -> None:
        """Test creating agent template without description - should be omitted."""
        agent_name = "Simple Agent"

        assert create_agent_template(agent_name=agent_name, path=str(tmp_path)) is True

        agent_folder = tmp_path / "simple_agent"
        agent_file = agent_folder / "simple_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")

        # Should NOT have description line
        assert "description=" not in agent_content
        assert f'name="{agent_name}"' in agent_content
        assert 'instructions="./instructions.md"' in agent_content

        # Instructions file should only have heading
        instructions_file = agent_folder / "instructions.md"
        instructions_content = instructions_file.read_text(encoding="utf-8")
        assert instructions_content == f"# {agent_name} Instructions\n\n"

    def test_agent_file_content_structure(self, tmp_path: Path) -> None:
        """Test that generated agent file has correct v1.x structure."""
        agent_name = "Data Processor"
        agent_description = "Processes and analyzes data"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
            )
            is True
        )

        agent_folder = tmp_path / "data_processor"
        agent_file = agent_folder / "data_processor.py"
        agent_content = agent_file.read_text(encoding="utf-8")

        # Check v1.x imports and structure
        assert "from agency_swarm import Agent, ModelSettings" in agent_content
        assert "data_processor = Agent(" in agent_content
        assert f'name="{agent_name}"' in agent_content
        assert f'description="{agent_description}"' in agent_content
        assert 'instructions="./instructions.md"' in agent_content
        assert 'files_folder="./files"' in agent_content
        assert 'tools_folder="./tools"' in agent_content
        assert 'model="gpt-4.1"' in agent_content  # Updated default model
        assert "ModelSettings(" in agent_content
        assert "temperature=0.3" in agent_content  # Should have default temperature for non-reasoning model

    def test_instructions_file_content(self, tmp_path: Path) -> None:
        """Test that instructions file has correct content."""
        agent_name = "Research Assistant"
        agent_description = "Helps with research tasks"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
            )
            is True
        )

        agent_folder = tmp_path / "research_assistant"
        instructions_file = agent_folder / "instructions.md"
        instructions_content = instructions_file.read_text(encoding="utf-8")

        assert f"# {agent_name} Instructions" in instructions_content
        assert f"You are {agent_name}" in instructions_content
        assert agent_description in instructions_content

    def test_custom_instructions(self, tmp_path: Path) -> None:
        """Test creating agent with custom instructions."""
        agent_name = "Custom Agent"
        agent_description = "Custom description"
        custom_instructions = "These are custom instructions for the agent."

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
                instructions=custom_instructions,
            )
            is True
        )

        agent_folder = tmp_path / "custom_agent"
        instructions_file = agent_folder / "instructions.md"
        instructions_content = instructions_file.read_text(encoding="utf-8")

        assert instructions_content == custom_instructions

    def test_custom_instructions_with_description(self, tmp_path: Path) -> None:
        """Test creating agent with custom instructions and description."""
        agent_name = "Custom Agent"
        agent_description = "Custom description"
        custom_instructions = "You are a specialized agent. Follow these rules: 1. Be precise 2. Be helpful"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                instructions=custom_instructions,
                path=str(tmp_path),
            )
            is True
        )

        agent_folder = tmp_path / "custom_agent"

        # Agent file should have description
        agent_file = agent_folder / "custom_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")
        assert f'description="{agent_description}"' in agent_content

        # Instructions file should have custom content (not auto-generated)
        instructions_file = agent_folder / "instructions.md"
        instructions_content = instructions_file.read_text(encoding="utf-8")
        assert instructions_content == custom_instructions

    def test_custom_instructions_without_description(self, tmp_path: Path) -> None:
        """Test creating agent with custom instructions but no description."""
        agent_name = "Instruction Agent"
        custom_instructions = "You are a specialized agent with custom instructions."

        assert (
            create_agent_template(agent_name=agent_name, instructions=custom_instructions, path=str(tmp_path)) is True
        )

        agent_folder = tmp_path / "instruction_agent"

        # Agent file should NOT have description
        agent_file = agent_folder / "instruction_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")
        assert "description=" not in agent_content

        # Instructions file should have custom content
        instructions_file = agent_folder / "instructions.md"
        instructions_content = instructions_file.read_text(encoding="utf-8")
        assert instructions_content == custom_instructions

    def test_use_txt_extension(self, tmp_path: Path) -> None:
        """Test creating agent with .txt instructions file."""
        agent_name = "Text Agent"
        agent_description = "Uses txt files"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
                use_txt=True,
            )
            is True
        )

        agent_folder = tmp_path / "text_agent"

        # Should create .txt file instead of .md
        assert (agent_folder / "instructions.txt").exists()
        assert not (agent_folder / "instructions.md").exists()

        # Agent file should reference .txt extension
        agent_file = agent_folder / "text_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")
        assert 'instructions="./instructions.txt"' in agent_content

    def test_without_example_tool(self, tmp_path: Path) -> None:
        """Test creating agent without example tool."""
        agent_name = "No Tool Agent"
        agent_description = "Agent without example tool"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
                include_example_tool=False,
            )
            is True
        )

        agent_folder = tmp_path / "no_tool_agent"

        # Should not create ExampleTool.py
        assert not (agent_folder / "tools" / "ExampleTool.py").exists()
        # But should still create tools folder and __init__.py
        assert (agent_folder / "tools").exists()
        assert (agent_folder / "tools" / "__init__.py").exists()

    def test_init_file_content(self, tmp_path: Path) -> None:
        """Test that __init__.py file has correct imports."""
        agent_name = "Import Test Agent"
        agent_description = "Test imports"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
            )
            is True
        )

        agent_folder = tmp_path / "import_test_agent"
        init_file = agent_folder / "__init__.py"
        init_content = init_file.read_text(encoding="utf-8")

        assert "from .import_test_agent import import_test_agent" in init_content

    def test_example_tool_content(self, tmp_path: Path) -> None:
        """Test that ExampleTool.py has correct v1.x structure."""
        agent_name = "Tool Test Agent"
        agent_description = "Test tool generation"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
            )
            is True
        )

        agent_folder = tmp_path / "tool_test_agent"
        tool_file = agent_folder / "tools" / "ExampleTool.py"
        tool_content = tool_file.read_text(encoding="utf-8")

        # Check v1.x tool structure
        assert "from agency_swarm.tools import BaseTool" in tool_content
        assert "from pydantic import Field" in tool_content
        assert "from dotenv import load_dotenv" in tool_content
        assert "load_dotenv()" in tool_content
        assert "class ExampleTool(BaseTool):" in tool_content
        assert "def run(self):" in tool_content
        assert 'if __name__ == "__main__":' in tool_content

    def test_folder_already_exists_error(self, tmp_path: Path) -> None:
        """Test that creating agent in existing folder raises error."""
        agent_name = "Existing Agent"
        agent_description = "Test existing folder"

        # Create the folder first
        (tmp_path / "existing_agent").mkdir()

        # Should raise exception
        with pytest.raises(FileExistsError, match="Folder already exists"):
            create_agent_template(agent_name=agent_name, agent_description=agent_description, path=str(tmp_path))

    def test_agent_name_normalization(self, tmp_path: Path) -> None:
        """Test that agent names with spaces are normalized correctly."""
        agent_name = "Complex Agent Name With Spaces"
        agent_description = "Test name normalization"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                path=str(tmp_path),
            )
            is True
        )

        # Should create folder with underscores
        agent_folder = tmp_path / "complex_agent_name_with_spaces"
        assert agent_folder.exists()

        # Check that agent variable is correct in files
        agent_file = agent_folder / "complex_agent_name_with_spaces.py"
        agent_content = agent_file.read_text(encoding="utf-8")
        assert "complex_agent_name_with_spaces = Agent(" in agent_content

        init_file = agent_folder / "__init__.py"
        init_content = init_file.read_text(encoding="utf-8")
        assert "from .complex_agent_name_with_spaces import complex_agent_name_with_spaces" in init_content

    @patch("builtins.input")
    def test_interactive_input(self, mock_input, tmp_path: Path) -> None:
        """Test interactive input when name not provided."""
        mock_input.return_value = "Interactive Agent"

        assert create_agent_template(path=str(tmp_path)) is True

        # Should create agent with input name
        agent_folder = tmp_path / "interactive_agent"
        assert agent_folder.exists()

        agent_file = agent_folder / "interactive_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")
        assert 'name="Interactive Agent"' in agent_content
        # Should NOT have description since we don't prompt for it anymore
        assert "description=" not in agent_content

    def test_reasoning_model_with_reasoning_parameter(self, tmp_path: Path) -> None:
        """Test creating agent with reasoning model and reasoning parameter."""
        agent_name = "Smart Agent"
        agent_description = "Uses reasoning capabilities"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                model="gpt-5-mini",
                reasoning="high",
                path=str(tmp_path),
            )
            is True
        )

        agent_folder = tmp_path / "smart_agent"
        agent_file = agent_folder / "smart_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")

        # Should have reasoning import and parameter
        assert "from openai.types.shared import Reasoning" in agent_content
        assert 'model="gpt-5-mini"' in agent_content
        assert 'reasoning=Reasoning(effort="high")' in agent_content
        # Should NOT have temperature
        assert "temperature=" not in agent_content

    def test_reasoning_model_with_temperature_shows_error(self, tmp_path: Path, capsys) -> None:
        """Test that reasoning model with temperature shows error but continues."""
        agent_name = "Bad Agent"
        agent_description = "Test error handling"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                model="gpt-5-mini",
                temperature=0.7,
                reasoning="medium",
                path=str(tmp_path),
            )
            is True
        )

        # Check error message was printed
        captured = capsys.readouterr()
        assert "ERROR: Reasoning models (like gpt-5-mini) do not support the temperature parameter" in captured.out
        assert "Temperature parameter will be ignored" in captured.out

        # Agent should still be created successfully
        agent_folder = tmp_path / "bad_agent"
        assert agent_folder.exists()

        agent_file = agent_folder / "bad_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")

        # Should have reasoning but no temperature
        assert 'reasoning=Reasoning(effort="medium")' in agent_content
        assert "temperature=" not in agent_content

    def test_non_reasoning_model_with_reasoning_shows_error(self, tmp_path: Path, capsys) -> None:
        """Test that non-reasoning model with reasoning shows error and ignores reasoning."""
        agent_name = "Regular Agent"
        agent_description = "Test error handling"

        assert (
            create_agent_template(
                agent_name=agent_name,
                agent_description=agent_description,
                model="gpt-4.1",
                reasoning="high",
                temperature=0.5,
                path=str(tmp_path),
            )
            is True
        )

        # Check error message was printed
        captured = capsys.readouterr()
        assert "ERROR: Non-reasoning models (like gpt-4.1) do not support the reasoning parameter" in captured.out
        assert "Reasoning parameter will be ignored" in captured.out

        # Agent should still be created successfully
        agent_folder = tmp_path / "regular_agent"
        assert agent_folder.exists()

        agent_file = agent_folder / "regular_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")

        # Should have temperature but no reasoning
        assert "temperature=0.5" in agent_content
        assert "reasoning=" not in agent_content
        assert "from openai.types.shared import Reasoning" not in agent_content

    @patch("builtins.input")
    def test_invalid_agent_name_validation(self, mock_input, tmp_path: Path, capsys) -> None:
        """Test that invalid agent names are rejected."""
        from agency_swarm.utils.create_agent_template import create_agent_template

        # Test empty name - should prompt for input, then validate
        mock_input.return_value = ""  # User enters empty string
        result = create_agent_template(agent_name=None, path=str(tmp_path))

        captured = capsys.readouterr()
        assert "ERROR: Agent name cannot be empty" in captured.out
        assert result is False

    def test_invalid_characters_in_name(self, tmp_path: Path, capsys) -> None:
        """Test that agent names with invalid characters show error."""
        from agency_swarm.utils.create_agent_template import create_agent_template

        # Test with invalid characters
        result = create_agent_template(agent_name="Bad<Name>", path=str(tmp_path))

        captured = capsys.readouterr()
        assert "ERROR: Agent name contains invalid characters" in captured.out
        assert result is False

    def test_temperature_validation(self, tmp_path: Path, capsys) -> None:
        """Test temperature validation."""
        from agency_swarm.utils.create_agent_template import create_agent_template

        # Test invalid temperature range
        result = create_agent_template(
            agent_name="Test Agent",
            temperature=3.0,  # Invalid: > 2.0
            path=str(tmp_path),
        )

        captured = capsys.readouterr()
        assert "ERROR: Temperature must be between 0.0 and 2.0" in captured.out
        assert result is False
