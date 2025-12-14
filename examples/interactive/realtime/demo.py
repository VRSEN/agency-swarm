"""
Interactive realtime voice demo.

Launches the packaged browser frontend + FastAPI backend.
Edit this file to customize the agent behavior.
"""

import sys
from pathlib import Path

# Ensure local src/ is importable when running directly from the repo checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

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
    print("Agency Swarm Realtime Browser Demo")
    print("=" * 50)
    print("Open http://localhost:8000 after launch.")
    print("Press Ctrl+C to stop.\n")

    RealtimeDemoLauncher.start(
        VOICE_AGENCY,
        model="gpt-realtime",
        voice="alloy",
        turn_detection={"type": "server_vad"},
    )


if __name__ == "__main__":
    main()
