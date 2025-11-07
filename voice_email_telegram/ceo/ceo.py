import os

from agents import ModelSettings

from agency_swarm import Agent

_current_dir = os.path.dirname(os.path.abspath(__file__))

ceo = Agent(
    name="CEO",
    description="Orchestrates the voice-to-email workflow and manages the approval state machine",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-5",
    model_settings=ModelSettings(
        max_tokens=25000,
        truncation="auto"  # Enables automatic context management
    )
)
