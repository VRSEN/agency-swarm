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

# Set to False to print raw SSE stream
PARSE_STREAM = True


def test_regular_endpoint():
    """Test the regular (non-streaming) endpoint."""
    print("\n" + "=" * 60)
    print("Testing Regular Endpoint: /my-agency/get_response")
    print("=" * 60)

    url = "http://localhost:8080/my-agency/get_response"

    # Initial request
    chat_history = []
    payload = {
        "message": "Hi, I'm John, can you ask the second agent to call ExampleTool?",
        "chat_history": chat_history,
    }

    print(f"\n📤 Request: {payload['message']}")
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Response: {data.get('response', 'No response')}")

        # Show new messages with agent metadata
        new_messages = data.get("new_messages", [])
        print(f"\nNew messages added ({len(new_messages)} total):")
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
    payload = {
        "message": "Hi, I'm John, can you ask the second agent to call ExampleTool?",
        "chat_history": chat_history,
    }

    print(f"\n📤 Request: {payload['message']}")
    print("\nStreaming events:")

    # Make streaming request
    response = requests.post(url, json=payload, stream=True)

    if response.status_code == 200:
        print("Streaming response:")
        accumulated_text = ""
        add_newline = False
        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8")
                if not PARSE_STREAM:
                    print(line_str)
                else:
                    # Parse SSE format
                    if line_str.startswith("data: "):
                        data_str = line_str[6:]  # Remove "data: " prefix

                        if data_str == "[DONE]":
                            print("\n\n✅ Stream complete")
                            break

                        try:
                            data = json.loads(data_str)

                            # Extract delta text from nested structure
                            if "data" in data and isinstance(data["data"], dict):
                                nested_data = data["data"]
                                if "data" in nested_data and isinstance(nested_data["data"], dict):
                                    inner_data = nested_data["data"]
                                    if "type" in inner_data and ".done" in inner_data["type"]:
                                        add_newline = True
                                    elif "delta" in inner_data:
                                        delta_text = inner_data["delta"]
                                        if isinstance(delta_text, str):
                                            if add_newline:
                                                print("\n")
                                            print(delta_text, end="", flush=True)
                                            accumulated_text += delta_text
                                            add_newline = False

                        except json.JSONDecodeError:
                            # Skip malformed JSON
                            pass

        print(f"\nSummary: Received {len(accumulated_text)} characters")
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
        print("\nAgency Structure:")
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
        test_regular_endpoint()
        test_streaming_endpoint()
        test_metadata_endpoint()

        print("\nDemo completed!")

    except requests.exceptions.ConnectionError:
        print("\n❌ Could not connect to server. Make sure it's running:")
        print("   python server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
