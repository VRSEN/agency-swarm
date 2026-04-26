"""
FastAPI Client Example for Agency Swarm v1.x

This client demonstrates how to interact with the FastAPI server,
including both regular and streaming responses, cancellation, and how to properly
handle the agent/callerAgent fields.

To run:
1. Start the server: python server.py
2. Run this client: python client.py
"""

import json
import time
from typing import Literal

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
        "message": "Hi, I'm John. Please ask the second agent to multiply 12 by 7.",
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


def cancel_stream(run_id: str, cancel_mode: str | None = None):
    """Cancel an active streaming run."""
    cancel_url = "http://localhost:8080/my-agency/cancel_response_stream"
    print(f"\n🛑 Cancelling run: {run_id} (mode={cancel_mode or 'immediate'})")

    try:
        payload = {"run_id": run_id}
        if cancel_mode is not None:
            payload["cancel_mode"] = cancel_mode
        response = requests.post(cancel_url, json=payload)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Cancel response: ok={data.get('ok')}, cancelled={data.get('cancelled')}")
            new_messages = data.get("new_messages", [])
            print(f"   Messages before cancel: {new_messages}")
            return data
        else:
            print(f"❌ Cancel failed: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Cancel error: {e}")
    return None


# Shared state for streaming thread
streaming_state = {
    "run_id": None,
    "completed": False,
    "cancelled": False,
    "accumulated_text": "",
}


def test_streaming_endpoint(message: str):
    """Test the streaming SSE endpoint."""
    print("\n" + "=" * 60)
    print("Testing Streaming Endpoint: /my-agency/get_response_stream")
    print("=" * 60)

    url = "http://localhost:8080/my-agency/get_response_stream"

    payload = {
        "message": message,
        "chat_history": [],
    }

    print(f"\n📤 Request: {payload['message']}")
    print("\nStreaming events:")

    response = requests.post(url, json=payload, stream=True)

    if response.status_code == 200:
        print("Streaming response:")
        accumulated_text = ""
        add_newline = False

        for line_str in response.iter_lines(chunk_size=1, decode_unicode=True):
            if line_str:
                if not PARSE_STREAM:
                    print(line_str)
                else:
                    if line_str.startswith("event: meta"):
                        continue

                    if line_str.startswith("data: "):
                        data_str = line_str[6:]

                        if data_str == "[DONE]":
                            print("\n\n✅ Stream complete")
                            break

                        try:
                            data = json.loads(data_str)

                            if "run_id" in data:
                                streaming_state["run_id"] = data["run_id"]
                                continue

                            if "new_messages" in data:
                                print(f"\n📨 Final messages: {len(data.get('new_messages', []))} messages")
                                continue

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
                            pass

        print(f"\nSummary: Received {len(accumulated_text)} characters")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def test_cancel_endpoint(cancel_mode: Literal["immediate", "after_turn"] | None = None):
    """Test cancelling a specific run_id (prompting the user when not provided)."""
    print("\n" + "=" * 60)
    print("Testing Cancel Endpoint")
    print("=" * 60)

    print("⚙️ Starting a streaming run to capture run_id automatically...")
    streaming_state["run_id"] = None
    streaming_state["completed"] = False
    streaming_state["cancelled"] = False
    streaming_state["accumulated_text"] = ""
    stream_url = "http://localhost:8080/my-agency/get_response_stream"
    stream_payload = {
        "message": "Write a 500 word poem.",
        "chat_history": [],
    }
    stream_response = requests.post(stream_url, json=stream_payload, stream=True)
    if stream_response.status_code != 200:
        print(f"❌ Could not start streaming run: {stream_response.status_code}")
        print(stream_response.text)
        return

    cancel_mode = cancel_mode or "immediate"
    cancel_url = "http://localhost:8080/my-agency/cancel_response_stream"
    accumulated_text = ""
    add_newline = False
    run_id = None
    cancelled = False

    print("⏳ Waiting for run_id...")
    for line_str in stream_response.iter_lines(chunk_size=1, decode_unicode=True):
        if not line_str:
            continue
        if not PARSE_STREAM:
            print(line_str)
        if line_str.startswith("event: meta"):
            continue
        if not line_str.startswith("data: "):
            continue

        data_str = line_str[6:]
        if data_str == "[DONE]":
            print("\n\n✅ Stream complete")
            break

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        if run_id is None and "run_id" in data:
            run_id = data["run_id"]
            streaming_state["run_id"] = run_id
            print(f"✅ Captured run_id: {run_id}")
            time.sleep(3)
            print(f"\n📤 Attempting to cancel run {run_id} (mode={cancel_mode})")
            payload = {"run_id": run_id, "cancel_mode": cancel_mode}
            response = requests.post(cancel_url, json=payload)
            if response.status_code == 404:
                print(f"✅ Correctly returned 404: {response.json()}")
            elif response.status_code == 200:
                cancelled = True
                payload = response.json()
                print("✅ Cancelled run; response payload:")
                print(json.dumps(payload, indent=2))
            else:
                print(f"❌ Unexpected status: {response.status_code}")
                print(response.text)
            continue

        if "new_messages" in data:
            print(f"\n📨 Final messages: {len(data.get('new_messages', []))} messages")
            continue

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

    stream_response.close()
    if run_id is None:
        print("❌ Timeout waiting for run_id; cannot demonstrate cancel endpoint.")
        return
    print(f"\nSummary: Received {len(accumulated_text)} characters before completion")
    if cancelled:
        print("🛑 Streaming helper request cancelled successfully.")


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
        # test_regular_endpoint()
        # test_streaming_endpoint(message="Hi, I'm John, can you ask the second agent to call ExampleTool?")
        # Change mode to "after_turn" to see alternative cancellation behavior
        test_cancel_endpoint(cancel_mode="immediate")
        # test_metadata_endpoint()

        print("\nDemo completed!")

    except requests.exceptions.ConnectionError:
        print("\n❌ Could not connect to server. Make sure it's running:")
        print("   python server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
