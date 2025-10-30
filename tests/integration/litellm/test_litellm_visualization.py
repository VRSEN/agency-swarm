"""
Integration test ensuring LiteLLM visualization redacts sensitive fields.
"""

import os

import pytest
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel

from agency_swarm import Agency, Agent

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY required for LiteLLM visualization test.",
)


def test_visualize_redacts_litellm_credentials(tmp_path):
    """Agency.visualize should not expose LiteLLM secrets in the generated HTML."""
    api_key = os.environ["OPENAI_API_KEY"]
    agent = Agent(
        name="Visualizer",
        instructions="Visualize the agency safely.",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="openai/gpt-4.1", api_key=api_key),
    )
    agency = Agency(agent)

    output_file = tmp_path / "visualization.html"
    result = agency.visualize(output_file=str(output_file), include_tools=False, open_browser=False)

    assert output_file.exists()
    assert result == str(output_file.resolve())

    html = output_file.read_text()
    assert "api_key" not in html
    assert api_key not in html
