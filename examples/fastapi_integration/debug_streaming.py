"""
Debug Streaming for FastAPI Integration

This script helps debug the streaming events and shows exactly what fields
are being sent in the SSE stream, particularly focusing on agent/callerAgent fields.

Run this after starting the server to see raw event data.
"""

import json

import requests


def debug_streaming() -> None:
    """Debug streaming to see exact event structure."""
    print("🔍 Debugging FastAPI Streaming Events")
    print("=" * 60)

    url = "http://localhost:8080/my-agency/get_response_stream"

    payload = {"message": "What's up, bro? Call the second agent to call ExampleTool", "chat_history": []}

    print(f"📤 Request: {payload['message']}\n")

    response = requests.post(url, json=payload, stream=True)

    if response.status_code == 200:
        event_count = 0

        # Track specific field occurrences
        agent_count = 0
        caller_agent_count = 0
        call_id_count = 0
        item_id_count = 0

        print("Raw events (first 20):\n")

        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8")

                if line_str.startswith("data: "):
                    data_str = line_str[6:]

                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        event_count += 1

                        # For final messages event
                        if "new_messages" in data:
                            print("\n=== FINAL MESSAGES EVENT ===")
                            print(f"Number of messages: {len(data['new_messages'])}")
                            for i, msg in enumerate(data["new_messages"][:3], 1):
                                print(f"\nMessage {i}:")
                                print(f"  agent: {msg.get('agent', None)}")
                                print(f"  callerAgent: {msg.get('callerAgent', None)}")
                                print(f"  type: {msg.get('type', msg.get('role', 'unknown'))}")
                            continue

                        # Show first 20 events in detail
                        if event_count <= 20:
                            print(f"\n--- Event #{event_count} ---")

                            # Check if data is wrapped
                            if "data" in data:
                                print("⚠️ Event is wrapped in 'data' field")
                                event_content = data["data"]
                            else:
                                event_content = data

                            # Check for our key fields
                            has_agent = "agent" in event_content
                            has_caller = "callerAgent" in event_content
                            has_call_id = "call_id" in event_content
                            has_item_id = "item_id" in event_content

                            if has_agent:
                                agent_count += 1
                                print(f"  agent: {event_content['agent']}")
                            else:
                                print("  agent: None")

                            if has_caller:
                                caller_agent_count += 1
                                print(f"  callerAgent: {event_content['callerAgent']}")
                            else:
                                print("  callerAgent: None")

                            if has_call_id:
                                call_id_count += 1
                                print(f"  call_id: {event_content['call_id'][:30]}...")

                            if has_item_id:
                                item_id_count += 1
                                print(f"  item_id: {event_content['item_id'][:30]}...")

                            # Show event type
                            if "type" in event_content:
                                print(f"   type: {event_content['type']}")

                            # Show nested structure if complex
                            if "data" in event_content and isinstance(event_content["data"], dict):
                                if "type" in event_content["data"]:
                                    print(f"   data.type: {event_content['data']['type']}")
                        else:
                            # Just count fields for remaining events
                            if "data" in data:
                                event_content = data["data"]
                            else:
                                event_content = data

                            if "agent" in event_content:
                                agent_count += 1
                            if "callerAgent" in event_content:
                                caller_agent_count += 1
                            if "call_id" in event_content:
                                call_id_count += 1
                            if "item_id" in event_content:
                                item_id_count += 1

                    except json.JSONDecodeError as e:
                        print(f"⚠️ JSON parse error: {e}")

        print("\n" + "=" * 60)
        print("📊 Field occurrence summary:")
        print(f"  Total events: {event_count}")
        print(f"  Events with 'agent': {agent_count} ({agent_count * 100 // max(event_count, 1)}%)")
        print(f"  Events with 'callerAgent': {caller_agent_count} ({caller_agent_count * 100 // max(event_count, 1)}%)")
        print(f"  Events with 'call_id': {call_id_count} ({call_id_count * 100 // max(event_count, 1)}%)")
        print(f"  Events with 'item_id': {item_id_count} ({item_id_count * 100 // max(event_count, 1)}%)")

        if agent_count < event_count * 0.8:
            print("\n⚠️ WARNING: Less than 80% of events have 'agent' field!")
            print("   This indicates the field is not being properly propagated.")
        else:
            print("\n✅ Good: Most events have the 'agent' field")

    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    try:
        debug_streaming()
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure it's running:")
        print("   python server.py")
    except Exception as e:
        print(f"❌ Error: {e}")
