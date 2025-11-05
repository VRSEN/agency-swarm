import os

from agency_swarm import Agent

_current_dir = os.path.dirname(os.path.abspath(__file__))

memory_manager = Agent(
    name="MemoryManager",
    description="Manages user preferences, supplier information, and contextual memory using Mem0",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-5",
    temperature=0.5,
    max_completion_tokens=25000,
)
