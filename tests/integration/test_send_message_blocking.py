"""
Integration test for SendMessage concurrent blocking behavior.
Tests both same-agent (blocking) and different-agent (no blocking) scenarios.
"""

import json

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


@pytest.mark.asyncio
async def test_concurrent_messages_to_same_agent():
    """
    Test sending 2 messages to the SAME subagent.
    This should trigger blocking due to per-recipient blocking mechanism.
    """
    # Track all events
    all_events = []

    def save_callback(messages):
        nonlocal all_events
        all_events = messages

    # Create test agents
    coordinator = Agent(
        name="Coordinator",
        instructions=(
            "When asked to test, immediately send TWO messages to Worker "
            "using send_message tool without waiting between calls. "
            "Message 1: 'First task', Message 2: 'Second task'"
        ),
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0.0),
    )

    worker = Agent(
        name="Worker",
        instructions="Reply with: 'Received: [the message you got]'",
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0.0),
    )

    # Create agency
    agency = Agency(
        coordinator,
        communication_flows=[(coordinator, worker)],
        save_threads_callback=save_callback,
    )

    blocking_detected = False
    tool_calls = []
    tool_outputs = []

    async for event in agency.get_response_stream("Test concurrent calls to same agent", agent_name="Coordinator"):
        # Check for function call outputs (these come as separate events)
        if hasattr(event, "type") and event.type == "function_call_output":
            output = str(event.output or "") if hasattr(event, "output") else ""
            if output:
                tool_outputs.append(output)
                print(f"  Function output: {output[:100]}")
                # Check for blocking
                if (
                    "cannot send another message" in output.lower()
                    or "concurrency violation" in output.lower()
                    or "sequentially" in output.lower()
                    or "still running" in output.lower()
                    or "still being processed" in output.lower()
                    or ("wait" in output.lower() and "respond" in output.lower())
                ):
                    blocking_detected = True
                    print("  BLOCKING DETECTED!")

        if hasattr(event, "item") and event.item:
            item = event.item

            # Track tool calls
            if hasattr(item, "type") and item.type == "tool_call_item":
                if hasattr(item, "raw_item"):
                    raw = item.raw_item
                    if hasattr(raw, "name") and raw.name == "send_message":
                        tool_calls.append(raw)
                        if hasattr(raw, "arguments"):
                            args = json.loads(raw.arguments)
                            recipient = args.get("recipient_agent", "?")
                            message = args.get("message", "?")[:50]
                            print(f"  Tool call: send_message to {recipient} - '{message}...'")

    print("\nResults:")
    print(f"  Tool calls made: {len(tool_calls)}")
    print(f"  Blocking detected: {blocking_detected}")

    # Analyze events for send_message attempts
    send_attempts = 0
    for event in all_events:
        if event.get("type") == "function_call" and event.get("name") == "send_message":
            send_attempts += 1

    print(f"  Send_message attempts in events: {send_attempts}")

    # If not detected in stream, check saved events for the blocking error
    if not blocking_detected:
        print("\n  Checking saved events for blocking...")
        for event in all_events:
            if event.get("type") == "function_call_output":
                output = str(event.get("output", ""))
                if output and (
                    "cannot send another message" in output.lower() or "still being processed" in output.lower()
                ):
                    blocking_detected = True
                    print(f"  BLOCKING DETECTED IN SAVED EVENTS: {output[:100]}")
                    break

    # The second concurrent message to the same agent should be blocked
    assert blocking_detected, "Second message to same agent should be blocked"


@pytest.mark.asyncio
async def test_messages_to_different_agents():
    """
    Test sending messages to TWO DIFFERENT agents.
    This should still work without errors (no blocking).
    """
    # Track all events
    all_events = []

    def save_callback(messages):
        nonlocal all_events
        all_events = messages

    # Create test agents
    coordinator = Agent(
        name="Coordinator",
        instructions=(
            "When asked to test, send one message to Worker1 and one message to Worker2. "
            "Message to Worker1: 'Task for worker 1', Message to Worker2: 'Task for worker 2'"
        ),
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0.0),
    )

    worker1 = Agent(
        name="Worker1",
        instructions="Reply with: 'Worker1 received: [the message]'",
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0.0),
    )

    worker2 = Agent(
        name="Worker2",
        instructions="Reply with: 'Worker2 received: [the message]'",
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0.0),
    )

    # Create agency with two communication flows
    agency = Agency(
        coordinator,
        communication_flows=[
            (coordinator, worker1),
            (coordinator, worker2),
        ],
        save_threads_callback=save_callback,
    )

    error_detected = False
    successful_calls = 0
    recipients_contacted = set()

    async for event in agency.get_response_stream("Test sending to different agents", agent_name="Coordinator"):
        if hasattr(event, "item") and event.item:
            item = event.item

            # Track tool calls
            if hasattr(item, "type") and item.type == "tool_call_item":
                if hasattr(item, "raw_item"):
                    raw = item.raw_item
                    if hasattr(raw, "name") and raw.name == "send_message":
                        if hasattr(raw, "arguments"):
                            args = json.loads(raw.arguments)
                            recipient = args.get("recipient_agent", "?")
                            message = args.get("message", "?")[:50]
                            print(f"  Tool call: send_message to {recipient} - '{message}...'")

                    if hasattr(raw, "output"):
                        output = str(raw.output or "")
                        if output:
                            print(f"  Output: {output[:100]}")
                            # Check for errors
                            if "error" in output.lower() and "cannot send" in output.lower():
                                error_detected = True
                                print("  ERROR DETECTED!")
                            elif "received" in output.lower():
                                successful_calls += 1
                                # Extract which worker responded
                                if "worker1" in output.lower():
                                    recipients_contacted.add("Worker1")
                                elif "worker2" in output.lower():
                                    recipients_contacted.add("Worker2")

    print("\nResults:")
    print(f"  Successful calls: {successful_calls}")
    print(f"  Recipients contacted: {recipients_contacted}")
    print(f"  Errors detected: {error_detected}")

    # Check saved events if nothing detected in stream
    if len(recipients_contacted) == 0:
        print("\n  Checking saved events for responses...")
        for event in all_events:
            if event.get("type") == "function_call_output":
                output = str(event.get("output", ""))
                if output:
                    # Check for errors
                    if "error" in output.lower() and "cannot send" in output.lower():
                        error_detected = True
                        print(f"  ERROR IN SAVED EVENTS: {output[:100]}")
                    elif "received" in output.lower():
                        if "worker1" in output.lower():
                            recipients_contacted.add("Worker1")
                            print("  Worker1 contacted (from saved events)")
                        elif "worker2" in output.lower():
                            recipients_contacted.add("Worker2")
                            print("  Worker2 contacted (from saved events)")

    # Messages to different agents should NOT be blocked
    assert not error_detected, "Messages to different agents should not be blocked"
    assert len(recipients_contacted) == 2, "Both Worker1 and Worker2 should be contacted"
