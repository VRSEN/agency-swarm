import json
import os
import subprocess
import sys
import time

import pytest
import requests

SERVER_START_TIMEOUT = 20
SERVER_PORT = 3088
SERVER_URL = f"http://localhost:{SERVER_PORT}"


@pytest.fixture(scope="module")
def fin_agency_server():
    """Start the fin_agency FastAPI app as a subprocess and tear it down after tests.

    Uses the same Python executable running tests so we don't accidentally use system
    interpreter. Ensures `src` is on PYTHONPATH so `agency_swarm` imports from local
    source directory.
    """
    cwd = os.getcwd()
    main_py = os.path.join(cwd, "tests", "integration", "fin_agency", "main.py")

    env = os.environ.copy()
    # Ensure local src is prioritized for imports
    env["PYTHONPATH"] = os.path.join(cwd, "src") + os.pathsep + env.get("PYTHONPATH", "")

    # Start server
    proc = subprocess.Popen([sys.executable, main_py], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # Wait until server is up
    start = time.time()
    up = False
    while time.time() - start < SERVER_START_TIMEOUT:
        try:
            r = requests.get(f"{SERVER_URL}/my-agency/get_metadata", timeout=1)
            if r.status_code == 200:
                up = True
                break
        except Exception:
            time.sleep(0.2)
    if not up:
        # capture some logs
        out = b""
        try:
            out = proc.stdout.read(1024)
        except Exception:
            pass
        proc.terminate()
        raise RuntimeError(f"fin_agency server failed to start. Log snippet: {out!r}")

    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


@pytest.mark.asyncio
async def test_fin_agency_send_message_agent_run_ids(fin_agency_server):
    """Run the Tesla prompt against the running fin_agency server and verify every
    runtime `send_message` function_call includes `agent_run_id`.
    """
    url = f"{SERVER_URL}/my-agency/get_response_stream"

    payload = {
        "message": "Please analyze Tesla (TSLA): fetch market data, delegate risk analysis, and format a report.",
        "recipient_agent": "PortfolioManager",
        "additional_instructions": "",
    }

    # Post and stream events; set read timeout longer than our read loop to avoid
    # urllib3 raising inside iter_lines. Use a tuple (connect_timeout, read_timeout).
    max_seconds = 30
    resp = requests.post(url, json=payload, stream=True, timeout=(10, max_seconds + 5))
    assert resp.status_code == 200

    send_message_occurrences = []
    runtime_like = []
    start = time.time()
    max_seconds = 30
    agent_updates = []
    saved_messages = []

    def recurse(obj, path=None, parent=None, results=None, top=None):
        if results is None:
            results = []
        if isinstance(obj, dict):
            if obj.get("name") == "send_message":
                results.append((path or [], obj, parent, top))
            for k, v in obj.items():
                recurse(v, (path or []) + [k], obj, results, top)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                recurse(v, (path or []) + [f"[{i}]"], obj, results, top)
        return results

    try:
        for raw in resp.iter_lines(decode_unicode=True):
            if time.time() - start > max_seconds:
                break
            if not raw:
                continue
            line = raw.strip()
            if line.startswith("data:"):
                js = line[len("data:") :].strip()
                try:
                    payload = json.loads(js)
                except Exception:
                    continue
                found = recurse(payload, top=payload)
                for path, obj, parent, top in found:
                    send_message_occurrences.append((path, obj, parent, top))
                    top_type = top.get("type") if isinstance(top, dict) else None
                    is_runtime = False
                    if top_type in (
                        "raw_response_event",
                        "response.in_progress",
                        "response.created",
                        "run_item_stream_event",
                    ):
                        is_runtime = True
                    if isinstance(parent, dict) and (
                        parent.get("type") == "function_call" or "call_id" in parent or "status" in parent
                    ):
                        is_runtime = True
                    if isinstance(obj, dict) and (
                        obj.get("type") == "function_call"
                        or "call_id" in obj
                        or obj.get("status") in ("in_progress", "completed")
                    ):
                        is_runtime = True
                    if is_runtime:
                        runtime_like.append((path, obj, parent, top))
                # record agent_updated_stream_event ids and agent_run_id for grouping
                if isinstance(payload, dict) and payload.get("type") == "agent_updated_stream_event":
                    # payload may have nested new_agent dict
                    new_agent = payload.get("new_agent")
                    agent_updates.append(
                        {
                            "id": payload.get("id"),
                            "agent": new_agent.get("name") if isinstance(new_agent, dict) else None,
                            "agent_run_id": payload.get("agent_run_id") or payload.get("id"),
                        }
                    )
                # capture 'messages' SSE event payload containing saved messages
                # some endpoints emit an event: messages then a data: {"new_messages": [...]}
                if isinstance(payload, dict) and "new_messages" in payload:
                    for m in payload.get("new_messages", []):
                        if isinstance(m, dict):
                            saved_messages.append(m)
            if line.startswith("event:") and line.endswith("end"):
                break
    except requests.exceptions.RequestException as e:
        # Treat stream read errors (timeouts, resets) as end-of-stream; we will
        # validate whatever we collected so far. This makes the test resilient to
        # network timing differences while still asserting agent_run_id presence.
        print("stream read error, proceeding with collected events:", e)
    finally:
        try:
            resp.close()
        except Exception:
            pass

    assert len(send_message_occurrences) >= 1, "No send_message occurrences found in stream"
    assert len(runtime_like) >= 1, "No runtime-like send_message function calls found in stream"

    missing = []

    def find_key(o, k):
        if isinstance(o, dict):
            if k in o:
                return o[k]
            for v in o.values():
                r = find_key(v, k)
                if r is not None:
                    return r
        if isinstance(o, list):
            for v in o:
                r = find_key(v, k)
                if r is not None:
                    return r
        return None

    for path, obj, parent, top in runtime_like:
        ar_top = find_key(top, "agent_run_id")
        ar_parent = find_key(parent, "agent_run_id") if parent is not None else None
        ar_obj = find_key(obj, "agent_run_id")
        if not (ar_top or ar_parent or ar_obj):
            missing.append({"path": ".".join(path), "obj_keys": list(obj.keys())})

    assert not missing, f"Found runtime send_message occurrences missing agent_run_id: {missing}"


@pytest.mark.asyncio
async def test_no_duplicate_function_calls_in_stream(fin_agency_server):
    """Test that streaming doesn't produce duplicate function_call events.

    This test verifies the fix for the bug where duplicate event handling
    caused duplicate function_call events to be saved, leading to 400 errors
    like 'No tool call found for function call output'.
    """
    # Use streaming endpoint directly to catch duplication errors faster
    stream_url = f"{SERVER_URL}/my-agency/get_response_stream"

    payload = {"message": "Please analyze TESLA (TSLA), SPY (SPY), and AMZN (AMZN)"}

    stream_resp = requests.post(stream_url, json=payload, stream=True, timeout=(10, 45))
    assert stream_resp.status_code == 200

    function_calls_by_id = {}
    function_call_outputs_by_id = {}
    error_found = None
    max_time = 45  # Maximum time to wait for response

    try:
        start_time = time.time()
        for raw in stream_resp.iter_lines(decode_unicode=True):
            if time.time() - start_time > max_time:
                break  # Timeout protection
            if not raw:
                continue
            line = raw.strip()
            if line.startswith("data:"):
                js = line[len("data:") :].strip()
                try:
                    event = json.loads(js)
                except Exception:
                    continue

                # Check for error events indicating the bug
                if isinstance(event, dict):
                    event_type = event.get("type")
                    if event_type == "error":
                        error_content = event.get("content", "")
                        if "No tool call found for function call output" in error_content:
                            error_found = error_content
                            break

                    # Track function calls and outputs from saved messages
                    if "new_messages" in event:
                        for msg in event.get("new_messages", []):
                            if isinstance(msg, dict):
                                msg_type = msg.get("type")
                                call_id = msg.get("call_id")

                                if msg_type == "function_call" and call_id:
                                    if call_id in function_calls_by_id:
                                        # Found duplicate!
                                        pytest.fail(
                                            f"Duplicate function_call found with call_id {call_id}. "
                                            f"This indicates the event handling duplication bug is present."
                                        )
                                    function_calls_by_id[call_id] = msg

                                elif msg_type == "function_call_output" and call_id:
                                    function_call_outputs_by_id[call_id] = msg

            if line.startswith("event:") and line.endswith("end"):
                break

    except requests.exceptions.RequestException:
        pass  # Stream ended, proceed with validation
    finally:
        try:
            stream_resp.close()
        except Exception:
            pass

    # Check if we found the specific error
    if error_found:
        pytest.fail(f"Found the duplicate function_call bug error: {error_found}")

    # Verify all function_calls have matching outputs (no orphaned calls)
    orphaned_calls = []
    for call_id, call_msg in function_calls_by_id.items():
        if call_id not in function_call_outputs_by_id:
            # send_message calls might not have outputs yet if they're in-progress
            if call_msg.get("name") != "send_message" or call_msg.get("status") == "completed":
                orphaned_calls.append(call_id)

    # Some tolerance for in-progress calls, but there shouldn't be many orphaned completed calls
    if len(orphaned_calls) > 3:
        pytest.fail(
            f"Found {len(orphaned_calls)} function_calls without matching outputs. "
            f"This may indicate incomplete processing. Orphaned call_ids: {orphaned_calls[:5]}..."
        )
