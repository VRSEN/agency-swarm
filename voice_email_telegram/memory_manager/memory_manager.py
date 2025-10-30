from agents import ModelSettings
from agency_swarm import Agent

memory_manager = Agent(
    name="MemoryManager",
    description="Manages user preferences, supplier information, and contextual memory using Mem0",
    instructions="./instructions.md",
    tools_folder="./tools",
    model_settings=ModelSettings(
        model="gpt-4o",
        temperature=0.5,
        max_completion_tokens=25000,
    ),
)
