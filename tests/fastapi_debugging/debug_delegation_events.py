#!/usr/bin/env python3
"""Show ALL events and saved messages - no filtering."""

import asyncio
import json

from agents import ModelSettings, function_tool

from agency_swarm import Agency, Agent


@function_tool
def analyze_data(data: str) -> str:
    return f"Analysis complete: {data}"


manager = Agent(
    name="Manager",
    instructions="When asked to delegate, use send_message to ask Worker: 'Please analyze this data: XYZ123'",
    model_settings=ModelSettings(temperature=0),
)

worker = Agent(
    name="Worker",
    instructions="When asked to analyze, use analyze_data tool, then respond 'Analysis completed.'",
    model_settings=ModelSettings(temperature=0),
    tools=[analyze_data],
)

agency = Agency(manager, communication_flows=[manager > worker])


async def main() -> None:
    # Track messages before
    before_count = len(agency.thread_manager.get_all_messages())

    print("=" * 80)
    print("STREAMING EVENTS")
    print("=" * 80)

    i = 0
    async for event in agency.get_response_stream("Please delegate", agent_name="Manager"):
        i += 1
        evt_type = getattr(event, "type", "?")
        agent = getattr(event, "agent", "")
        agent_run_id = getattr(event, "agent_run_id", "")
        parent_run_id = getattr(event, "parent_run_id", "")

        # Extract item info
        item_type = ""
        tool_name = ""
        call_id = ""
        content = ""
        if hasattr(event, "item") and event.item:
            item = event.item
            item_type = getattr(item, "type", "")
            if hasattr(item, "raw_item") and item.raw_item:
                raw = item.raw_item
                tool_name = getattr(raw, "name", "")
                call_id = getattr(raw, "call_id", "")
                if hasattr(raw, "content") and raw.content:
                    content = str(raw.content[0].text if raw.content[0].text else "")[:30]

        # Extract data info
        data_type = ""
        delta = ""
        if hasattr(event, "data"):
            data = event.data
            data_type = str(getattr(data, "type", ""))
            delta = str(getattr(data, "delta", ""))[:50]

        # Build output line
        parts = [f"{i:3}"]
        if evt_type:
            parts.append(f"type={evt_type}")
        if item_type:
            parts.append(f"item={item_type}")
        if data_type:
            parts.append(f"data={data_type}")
        if agent:
            parts.append(f"agent={agent}")
        if tool_name:
            parts.append(f"tool={tool_name}")
        if delta:
            parts.append(f"delta={delta}")
        if content:
            parts.append(f"content={content}")
        if call_id:
            parts.append(f"call_id={call_id}")
        if agent_run_id:
            parts.append(f"agent_run_id={agent_run_id}")
        if parent_run_id:
            parts.append(f"parent_run_id={parent_run_id}")

        print(" | ".join(parts))

    print(f"\nTotal streaming events: {i}")

    # Show saved messages
    print("\n" + "=" * 80)
    print("SAVED MESSAGES (new_messages)")
    print("=" * 80)

    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before_count:]

    for j, msg in enumerate(new_messages, 1):
        msg_type = msg.get("type", "")
        role = msg.get("role", "")
        agent = msg.get("agent", "")
        name = msg.get("name", "")
        call_id = msg.get("call_id", "")
        agent_run_id = msg.get("agent_run_id", "")
        parent_run_id = msg.get("parent_run_id", "")

        # Extract content/arguments
        content_preview = ""
        if msg_type == "function_call":
            args = msg.get("arguments", "{}")
            try:
                args_dict = json.loads(args)
                if "recipient_agent" in args_dict:
                    content_preview = f"to={args_dict['recipient_agent']}"
            except Exception:
                content_preview = args[:50]
        elif role == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                content_preview = content[:50]
            elif isinstance(content, list) and content:
                content_preview = str(content[0])[:50]

        # Build message line
        parts = [f"{j:3}"]
        if msg_type:
            parts.append(f"type={msg_type}")
        if role:
            parts.append(f"role={role}")
        if agent:
            parts.append(f"agent={agent}")
        if name:
            parts.append(f"name={name}")
        if content_preview:
            parts.append(f"preview={content_preview}")
        if call_id:
            parts.append(f"call_id={call_id}")
        if agent_run_id:
            parts.append(f"agent_run_id={agent_run_id}")
        if parent_run_id:
            parts.append(f"parent_run_id={parent_run_id}")

        print(" | ".join(parts))

    print(f"\nTotal saved messages: {len(new_messages)}")


if __name__ == "__main__":
    asyncio.run(main())
