from agents import ModelSettings
from agency_swarm import Agent

email_specialist = Agent(
    name="EmailSpecialist",
    description="Drafts professional emails from voice input and manages Gmail operations",
    instructions="./instructions.md",
    tools_folder="./tools",
    model_settings=ModelSettings(
        model="gpt-4o",
        temperature=0.5,
        max_completion_tokens=25000,
    ),
)
