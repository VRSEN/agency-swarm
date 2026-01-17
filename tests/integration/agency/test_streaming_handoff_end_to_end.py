import os

import pytest
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel

from agency_swarm import Agency, Agent
from agency_swarm.tools.send_message import SendMessageHandoff

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY required for live streaming handoff test.",
)


@pytest.mark.asyncio
async def test_streaming_handoff_end_to_end_injects_reminder_and_completes():
    import litellm

    litellm.modify_params = True

    sender = Agent(
        name="Sender",
        instructions=(
            "Immediately transfer to Recipient using the transfer tool. "
            "Do not do anything else."
        ),
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    )
    recipient = Agent(
        name="Recipient",
        instructions="Reply with exactly: done",
        model_settings=ModelSettings(temperature=0.0),
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    )

    agency = Agency(
        sender,
        recipient,
        communication_flows=[(sender > recipient, SendMessageHandoff)],
        shared_instructions="Test agency",
    )

    stream = agency.get_response_stream(message="transfer to recipient", recipient_agent="Sender")
    async for _event in stream:
        pass

    final = await stream.wait_final_result()
    assert final is not None
    assert isinstance(final.final_output, str)
    assert "done" in final.final_output.lower()

    assert any(
        isinstance(m.get("message_origin"), str) and m.get("message_origin") == "handoff_reminder"
        for m in agency.thread_manager.get_all_messages()
    )

