"""
Interactive realtime voice demo.

Launches the packaged browser frontend + FastAPI backend.
Edit this file to customize the agent behavior.
"""

import os
import sys
from pathlib import Path

# Ensure local src/ is importable when running directly from the repo checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agency_swarm import Agency, Agent, function_tool
from agency_swarm.ui.demos.realtime import RealtimeDemoLauncher


@function_tool
def lookup_order(order_id: str) -> str:
    """Return a short order status by ID."""
    return f"Order {order_id} has shipped and will arrive soon."


VOICE_AGENT = Agent(
    name="Voice Concierge",
    instructions=(
        "You are a helpful voice concierge. Answer succinctly and offer to look up order details "
        "with the provided tool when asked about an order number."
    ),
    tools=[lookup_order],
)

VOICE_AGENCY = Agency(VOICE_AGENT)


def main() -> None:
    provider = os.getenv("REALTIME_PROVIDER", "openai").strip().lower()
    if provider not in {"openai", "xai"}:
        raise ValueError("REALTIME_PROVIDER must be 'openai' or 'xai'.")

    default_model = "grok-voice-agent" if provider == "xai" else "gpt-realtime"
    default_voice = "rex" if provider == "xai" else "alloy"
    model = os.getenv("REALTIME_MODEL", default_model).strip()
    voice = os.getenv("REALTIME_VOICE", default_voice).strip()

    turn_detection = {
        "type": "server_vad",
        "create_response": True,
        "interrupt_response": True,
    }
    if provider == "xai":
        # Recommended xAI defaults for stable interruption behavior.
        turn_detection.update(
            {
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 200,
            }
        )

    print("Agency Swarm Realtime Browser Demo")
    print("=" * 50)
    print(f"Provider: {provider}")
    print(f"Model: {model}")
    print(f"Voice: {voice}")
    print("Open http://localhost:8000 after launch.")
    print("Press Ctrl+C to stop.\n")

    RealtimeDemoLauncher.start(
        VOICE_AGENCY,
        provider=provider,
        model=model,
        voice=voice,
        turn_detection=turn_detection,
    )


if __name__ == "__main__":
    main()
