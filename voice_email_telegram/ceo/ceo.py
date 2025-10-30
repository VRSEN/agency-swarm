from agents import ModelSettings
from agency_swarm import Agent

ceo = Agent(
    name="CEO",
    description="Orchestrates the voice-to-email workflow and manages the approval state machine",
    instructions="./instructions.md",
    tools_folder="./tools",
    model_settings=ModelSettings(
        model="gpt-4o",
        temperature=0.5,
        max_completion_tokens=25000,
    ),
)
