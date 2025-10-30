from agents import ModelSettings
from agency_swarm import Agent

voice_handler = Agent(
    name="VoiceHandler",
    description="Processes voice input from Telegram and generates voice confirmations via ElevenLabs",
    instructions="./instructions.md",
    tools_folder="./tools",
    model_settings=ModelSettings(
        model="gpt-4o",
        temperature=0.5,
        max_completion_tokens=25000,
    ),
)
