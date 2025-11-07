import os

from agents import ModelSettings

from agency_swarm import Agent

_current_dir = os.path.dirname(os.path.abspath(__file__))

voice_handler = Agent(
    name="VoiceHandler",
    description="Processes voice input from Telegram and generates voice confirmations via ElevenLabs",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-5",
    model_settings=ModelSettings(
        max_tokens=25000,
        truncation="auto"
    )
)
