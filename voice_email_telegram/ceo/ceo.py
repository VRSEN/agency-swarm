from agency_swarm import Agent
import os

_current_dir = os.path.dirname(os.path.abspath(__file__))

ceo = Agent(
    name="CEO",
    description="Orchestrates the voice-to-email workflow and manages the approval state machine",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-4o",
    temperature=0.5,
    max_completion_tokens=25000,
)
