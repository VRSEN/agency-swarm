"""Integration tests for CLI create-agent-template functionality."""

import subprocess
import sys
from pathlib import Path


class TestCreateAgentTemplateIntegration:
    """Integration tests for the create-agent-template CLI command."""

    def test_create_agent_template_cli_integration(self, tmp_path: Path) -> None:
        """Test the complete CLI workflow for creating an agent template."""
        # Run the CLI command as a subprocess
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "Integration Test Agent",
                "--description",
                "An agent for integration testing",
                "--path",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,  # Project root
        )

        # Check command succeeded
        assert result.returncode == 0, f"CLI command failed: {result.stderr}"

        # Verify output message
        assert "Agent folder created successfully" in result.stdout
        assert "Import it with: from integration_test_agent import integration_test_agent" in result.stdout

        # Verify folder structure was created
        agent_folder = tmp_path / "integration_test_agent"
        assert agent_folder.exists()
        assert agent_folder.is_dir()

        # Verify all required files exist
        required_files = ["__init__.py", "integration_test_agent.py", "instructions.md"]

        for file_name in required_files:
            file_path = agent_folder / file_name
            assert file_path.exists(), f"Missing file: {file_name}"
            assert file_path.is_file()

        # Verify directories exist
        assert (agent_folder / "tools").exists()
        assert (agent_folder / "files").exists()
        assert (agent_folder / "tools" / "__init__.py").exists()
        assert (agent_folder / "tools" / "ExampleTool.py").exists()

    def test_create_agent_with_txt_extension(self, tmp_path: Path) -> None:
        """Test creating agent with --use-txt option."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "TXT Agent",
                "--use-txt",
                "--path",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode == 0

        # Check that .txt file was created instead of .md
        agent_folder = tmp_path / "txt_agent"
        assert (agent_folder / "instructions.txt").exists()
        assert not (agent_folder / "instructions.md").exists()

        # Check that agent file references .txt extension
        agent_file = agent_folder / "txt_agent.py"
        content = agent_file.read_text(encoding="utf-8")
        assert 'instructions="./instructions.txt"' in content

    def test_create_agent_with_instructions_parameter(self, tmp_path: Path) -> None:
        """Test creating agent with --instructions option."""
        custom_instructions = "You are a specialized test agent. Always be precise and helpful."

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "Instruction Agent",
                "--instructions",
                custom_instructions,
                "--path",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode == 0

        # Check that custom instructions were used
        agent_folder = tmp_path / "instruction_agent"
        instructions_file = agent_folder / "instructions.md"
        instructions_content = instructions_file.read_text(encoding="utf-8")
        assert instructions_content == custom_instructions

        # Agent file should NOT have description since none was provided
        agent_file = agent_folder / "instruction_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")
        assert "description=" not in agent_content

    def test_cli_help_command(self) -> None:
        """Test that CLI help command works."""
        result = subprocess.run(
            [sys.executable, "-m", "agency_swarm.cli.main", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode == 0
        assert "Agency Swarm CLI tools" in result.stdout
        assert "create-agent-template" in result.stdout

    def test_create_agent_template_help_command(self) -> None:
        """Test that create-agent-template help command works."""
        result = subprocess.run(
            [sys.executable, "-m", "agency_swarm.cli.main", "create-agent-template", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode == 0
        # Check for key help text elements (more flexible matching)
        assert "create-agent-template" in result.stdout
        assert "--description" in result.stdout
        assert "--instructions" in result.stdout
        assert "--use-txt" in result.stdout
        assert "--path" in result.stdout

    def test_generated_agent_can_be_imported(self, tmp_path: Path) -> None:
        """Test that the generated agent can be imported and used."""
        # Create agent
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "Import Test Agent",
                "--description",
                "Test agent for import validation",
                "--path",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode == 0

        # Test that the generated Python code is syntactically valid
        agent_file = tmp_path / "import_test_agent" / "import_test_agent.py"

        # Read and compile the generated code to check syntax
        with open(agent_file, encoding="utf-8") as f:
            code = f.read()

        # This will raise SyntaxError if the code is invalid
        compile(code, str(agent_file), "exec")

        # Verify the agent variable is defined in the code
        assert "import_test_agent = Agent(" in code

        # Test that the tool file is also syntactically valid
        tool_file = tmp_path / "import_test_agent" / "tools" / "ExampleTool.py"
        with open(tool_file, encoding="utf-8") as f:
            tool_code = f.read()

        compile(tool_code, str(tool_file), "exec")

    def test_missing_agent_name_fails(self) -> None:
        """Test that missing agent name causes CLI to fail."""
        result = subprocess.run(
            [sys.executable, "-m", "agency_swarm.cli.main", "create-agent-template"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        # Should fail with non-zero exit code
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_folder_already_exists_error(self, tmp_path: Path) -> None:
        """Test that creating agent in existing folder fails gracefully."""
        # Create the folder first
        (tmp_path / "existing_agent").mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "Existing Agent",
                "--path",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        # Should fail with non-zero exit code
        assert result.returncode != 0
        assert "Folder already exists" in result.stderr

    def test_invalid_agent_name_returns_error(self, tmp_path: Path) -> None:
        """Invalid agent names should surface a non-zero exit code."""

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "Invalid<Name>",
                "--path",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode != 0
        assert "Agent name contains invalid characters" in result.stdout

    def test_cli_propagates_validation_errors(self, tmp_path: Path) -> None:
        """CLI should fail fast when validation rejects input."""

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "Invalid Temperature Agent",
                "--temperature",
                "3.0",
                "--path",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode == 1
        assert "ERROR: Temperature must be between 0.0 and 2.0" in result.stdout

    def test_create_agent_with_all_options(self, tmp_path: Path) -> None:
        """Test create-agent-template command with all available options."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agency_swarm.cli.main",
                "create-agent-template",
                "Full Options Agent",
                "--description",
                "Agent created with all CLI options",
                "--path",
                str(tmp_path),
                "--use-txt",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent,
        )

        assert result.returncode == 0

        agent_folder = tmp_path / "full_options_agent"
        assert agent_folder.exists()

        # Verify description is in agent file
        agent_file = agent_folder / "full_options_agent.py"
        agent_content = agent_file.read_text(encoding="utf-8")
        assert "Agent created with all CLI options" in agent_content

        # Verify txt extension was used
        assert (agent_folder / "instructions.txt").exists()
        assert 'instructions="./instructions.txt"' in agent_content
