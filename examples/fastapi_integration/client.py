"""
FastAPI Client Example for Agency Swarm v1.x

This client demonstrates how to interact with the FastAPI server,
including both regular and streaming responses, and how to properly
handle the agent/callerAgent fields.

To run:
1. Start the server: python server.py
2. Run this client: python client.py
"""

import json
import time

import requests


def test_regular_endpoint():
    """Test the regular (non-streaming) endpoint."""
    print("\n" + "=" * 60)
    print("Testing Regular Endpoint: /my-agency/get_response")
    print("=" * 60)

    url = "http://localhost:8080/my-agency/get_response"

    # Initial request
    chat_history = []
    payload = {"message": "What's up, bro? Call the second agent to call ExampleTool", "chat_history": chat_history}

    print(f"\n📤 Request: {payload['message']}")
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Response: {data.get('response', 'No response')}")

        # Show new messages with agent metadata
        new_messages = data.get("new_messages", [])
        print(f"\n📋 New messages added ({len(new_messages)} total):")
        for i, msg in enumerate(new_messages, 1):
            print(f"\n  Message {i}:")
            print(f"    Agent: {msg.get('agent', 'N/A')}")
            print(f"    CallerAgent: {msg.get('callerAgent', 'N/A')}")
            print(f"    Type: {msg.get('type', msg.get('role', 'unknown'))}")
            if "content" in msg:
                content = msg["content"]
                if isinstance(content, list) and content:
                    text = content[0].get("text", "") if isinstance(content[0], dict) else str(content[0])
                else:
                    text = str(content)
                print(f"    Content: {text[:100]}...")
            elif "name" in msg:
                print(f"    Tool: {msg['name']}")
                if "arguments" in msg:
                    print(f"    Arguments: {msg['arguments'][:100]}...")

        # Update chat history for next request
        chat_history.extend(new_messages)
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def test_streaming_endpoint():
    """Test the streaming SSE endpoint."""
    print("\n" + "=" * 60)
    print("Testing Streaming Endpoint: /my-agency/get_response_stream")
    print("=" * 60)

    url = "http://localhost:8080/my-agency/get_response_stream"

    chat_history = []
    payload = {"message": "What's up, bro? Call the second agent to call ExampleTool", "chat_history": chat_history}

    print(f"\n📤 Request: {payload['message']}")
    print("\n🔄 Streaming events:")

    # Make streaming request
    response = requests.post(url, json=payload, stream=True)

    if response.status_code == 200:
        event_count = 0
        agent_events = {}  # Track events by agent

        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8")

                # Parse SSE format
                if line_str.startswith("data: "):
                    data_str = line_str[6:]  # Remove "data: " prefix

                    if data_str == "[DONE]":
                        print("\n✅ Stream complete")
                        break

                    try:
                        data = json.loads(data_str)
                        event_count += 1

                        # Check if this is the final messages event
                        if "new_messages" in data:
                            new_messages = data["new_messages"]
                            print(f"\n📋 Final: Received {len(new_messages)} new messages")
                            for msg in new_messages[:3]:  # Show first 3 messages
                                print(
                                    f"  - Agent: {msg.get('agent', 'N/A')}, "
                                    f"CallerAgent: {msg.get('callerAgent', 'N/A')}, "
                                    f"Type: {msg.get('type', msg.get('role', 'unknown'))}"
                                )
                        else:
                            # Regular streaming event
                            event_data = data.get("data", data)

                            # Extract metadata fields
                            agent = event_data.get("agent", "N/A")
                            caller_agent = event_data.get("callerAgent", "N/A")
                            call_id = event_data.get("call_id", "")
                            item_id = event_data.get("item_id", "")

                            # Track events by agent
                            if agent != "N/A":
                                if agent not in agent_events:
                                    agent_events[agent] = 0
                                agent_events[agent] += 1

                            # Show first few events and important ones
                            if event_count <= 10 or call_id or item_id:
                                print(f"\n  Event #{event_count}:")
                                print(f"    Agent: {agent}")
                                print(f"    CallerAgent: {caller_agent}")
                                if call_id:
                                    print(f"    call_id: {call_id[:20]}...")
                                if item_id:
                                    print(f"    item_id: {item_id[:20]}...")

                                # Show event type if available
                                if "type" in event_data:
                                    print(f"    Type: {event_data['type']}")
                                elif "data" in event_data and isinstance(event_data["data"], dict):
                                    if "type" in event_data["data"]:
                                        print(f"    Type: {event_data['data']['type']}")

                            elif event_count == 11:
                                print("\n  ... (showing only events with IDs from now on) ...")

                    except json.JSONDecodeError as e:
                        print(f"⚠️ Failed to parse JSON: {e}")
                        print(f"   Raw: {data_str[:100]}...")

                elif line_str.startswith("event: "):
                    event_type = line_str[7:]  # Remove "event: " prefix
                    if event_type != "end":
                        print(f"\n🎯 Event type: {event_type}")

        print("\n📊 Summary:")
        print(f"  Total events: {event_count}")
        print(f"  Events by agent: {agent_events}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def test_metadata_endpoint():
    """Test the metadata endpoint."""
    print("\n" + "=" * 60)
    print("Testing Metadata Endpoint: /my-agency/get_metadata")
    print("=" * 60)

    url = "http://localhost:8080/my-agency/get_metadata"

    response = requests.get(url)

    if response.status_code == 200:
        metadata = response.json()
        print("\n📊 Agency Structure:")
        print(json.dumps(metadata, indent=2))
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def main():
    """Run all tests."""
    print("🧪 Agency Swarm FastAPI Client Test")
    print("=" * 60)
    print("Make sure the server is running on http://localhost:8080")
    print("=" * 60)

    # Wait a moment for server to be ready
    time.sleep(1)

    try:
        # Test all endpoints
        test_metadata_endpoint()
        test_regular_endpoint()
        test_streaming_endpoint()

        print("\n✅ All tests completed!")

    except requests.exceptions.ConnectionError:
        print("\n❌ Could not connect to server. Make sure it's running:")
        print("   python server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
