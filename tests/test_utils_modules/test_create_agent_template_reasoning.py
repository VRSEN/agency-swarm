"""Tests for create_agent_template reasoning and validation behavior."""

from pathlib import Path
from unittest.mock import patch

from agency_swarm.utils.create_agent_template import create_agent_template


class TestCreateAgentTemplateReasoning:
    def test_reasoning_model_with_reasoning_parameter(self, tmp_path: Path) -> None:
        """Test creating agent with reasoning model and reasoning parameter."""
        assert (
            create_agent_template(
                agent_name="Smart Agent",
                agent_description="Uses reasoning capabilities",
                model="gpt-5.4-mini",
                reasoning="high",
                path=str(tmp_path),
            )
            is True
        )

        agent_content = (tmp_path / "smart_agent" / "smart_agent.py").read_text(encoding="utf-8")
        assert "from openai.types.shared import Reasoning" in agent_content
        assert 'model="gpt-5.4-mini"' in agent_content
        assert 'reasoning=Reasoning(effort="high", summary="auto")' in agent_content
        assert "temperature=" not in agent_content

    def test_reasoning_model_with_temperature_shows_error(self, tmp_path: Path, capsys) -> None:
        """Test that reasoning model with temperature shows error but continues."""
        assert (
            create_agent_template(
                agent_name="Bad Agent",
                agent_description="Test error handling",
                model="gpt-5.4-mini",
                temperature=0.7,
                reasoning="medium",
                path=str(tmp_path),
            )
            is True
        )

        captured = capsys.readouterr()
        assert "ERROR: Reasoning models (like gpt-5.4-mini) do not support the temperature parameter" in captured.out
        assert "Temperature parameter will be ignored" in captured.out

        agent_content = (tmp_path / "bad_agent" / "bad_agent.py").read_text(encoding="utf-8")
        assert 'reasoning=Reasoning(effort="medium", summary="auto")' in agent_content
        assert "temperature=" not in agent_content

    def test_non_reasoning_model_with_reasoning_shows_error(self, tmp_path: Path, capsys) -> None:
        """Test that non-reasoning model with reasoning shows error and ignores reasoning."""
        assert (
            create_agent_template(
                agent_name="Regular Agent",
                agent_description="Test error handling",
                model="gpt-4.1",
                reasoning="high",
                temperature=0.5,
                path=str(tmp_path),
            )
            is True
        )

        captured = capsys.readouterr()
        assert "ERROR: Non-reasoning models (like gpt-4.1) do not support the reasoning parameter" in captured.out
        assert "Reasoning parameter will be ignored" in captured.out

        agent_content = (tmp_path / "regular_agent" / "regular_agent.py").read_text(encoding="utf-8")
        assert "temperature=0.5" in agent_content
        assert "reasoning=" not in agent_content
        assert "from openai.types.shared import Reasoning" not in agent_content

    @patch("builtins.input")
    def test_invalid_agent_name_validation(self, mock_input, tmp_path: Path, capsys) -> None:
        """Test that invalid agent names are rejected."""
        mock_input.return_value = ""
        result = create_agent_template(agent_name=None, path=str(tmp_path))

        captured = capsys.readouterr()
        assert "ERROR: Agent name cannot be empty" in captured.out
        assert result is False

    def test_invalid_characters_in_name(self, tmp_path: Path, capsys) -> None:
        """Test that agent names with invalid characters show error."""
        result = create_agent_template(agent_name="Bad<Name>", path=str(tmp_path))

        captured = capsys.readouterr()
        assert "ERROR: Agent name contains invalid characters" in captured.out
        assert result is False

    def test_temperature_validation(self, tmp_path: Path, capsys) -> None:
        """Test temperature validation."""
        result = create_agent_template(agent_name="Test Agent", temperature=3.0, path=str(tmp_path))

        captured = capsys.readouterr()
        assert "ERROR: Temperature must be between 0.0 and 2.0" in captured.out
        assert result is False

    def test_description_with_quotes_escaped(self, tmp_path: Path) -> None:
        """Test that quotes in description are properly escaped in instructions."""
        assert (
            create_agent_template(
                agent_name="Quote Agent",
                agent_description='An agent that uses "quotes" in description',
                path=str(tmp_path),
            )
            is True
        )

        instructions = (tmp_path / "quote_agent" / "instructions.md").read_text(encoding="utf-8")
        assert "An agent that uses 'quotes' in description" in instructions
        assert 'An agent that uses "quotes" in description' not in instructions

    def test_gpt5_reasoning_includes_summary(self, tmp_path: Path) -> None:
        """Test that GPT-5 models include summary parameter in Reasoning."""
        assert (
            create_agent_template(
                agent_name="GPT5 Agent",
                model="gpt-5.4-mini",
                reasoning="high",
                path=str(tmp_path),
            )
            is True
        )

        agent_content = (tmp_path / "gpt5_agent" / "gpt5_agent.py").read_text(encoding="utf-8")
        assert 'Reasoning(effort="high", summary="auto")' in agent_content
        assert "temperature=" not in agent_content

    def test_non_gpt5_reasoning_no_summary(self, tmp_path: Path) -> None:
        """Test that non-GPT-5 reasoning models don't include summary in Reasoning."""
        assert (
            create_agent_template(
                agent_name="O1 Agent",
                model="o1-preview",
                reasoning="high",
                path=str(tmp_path),
            )
            is True
        )

        agent_content = (tmp_path / "o1_agent" / "o1_agent.py").read_text(encoding="utf-8")
        assert 'Reasoning(effort="high")' in agent_content
        assert 'summary="auto"' not in agent_content
        assert "temperature=" not in agent_content
