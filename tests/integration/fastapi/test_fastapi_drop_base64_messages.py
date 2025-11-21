"""
Integration test for FastAPI drop_base64_messages functionality.

This test verifies that when drop_base64_messages is enabled, messages containing
base64 multimodal outputs and their corresponding tool call messages are removed
from the response history.
"""

import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from agents import ModelSettings

from agency_swarm import Agency, Agent, BaseTool
from agency_swarm.tools.utils import tool_output_image_from_path


class LoadTestImage(BaseTool):
    """Return a test image as a multimodal output with base64 data."""

    def run(self):
        image_file = Path(__file__).resolve().parents[2] / "data" / "files" / "test-image.png"
        return tool_output_image_from_path(image_file, detail="auto")


class TestFastAPIDropBase64Messages:
    """Test suite for drop_base64_messages functionality."""

    @staticmethod
    def get_http_client(timeout_seconds: int = 120) -> httpx.AsyncClient:
        """Create an HTTP client with proper timeout configuration."""
        timeout_config = httpx.Timeout(
            timeout_seconds,
            connect=10.0,
            read=timeout_seconds,
            write=10.0,
            pool=5.0,
        )
        return httpx.AsyncClient(timeout=timeout_config)

    @pytest.fixture(scope="class")
    def agency_factory(self):
        """Create an agency factory with a tool that returns base64 images."""

        def create_agency(load_threads_callback=None, save_threads_callback=None):
            agent = Agent(
                name="ImageAgent",
                instructions="When asked to load an image, use the LoadTestImage tool.",
                description="Agent that loads and returns images",
                tools=[LoadTestImage],
                model_settings=ModelSettings(temperature=0),
            )

            return Agency(
                agent,
                load_threads_callback=load_threads_callback,
                save_threads_callback=save_threads_callback,
            )

        return create_agency

    @pytest.fixture(scope="class")
    def fastapi_server_with_drop_enabled(self, agency_factory):
        """Start FastAPI server with drop_base64_messages enabled."""
        import threading

        from agency_swarm import run_fastapi

        app = run_fastapi(
            agencies={"test_agency": agency_factory},
            app_token_env="",
            return_app=True,
            drop_base64_messages=True,
        )

        def run_server():
            uvicorn.run(app, host="127.0.0.1", port=8080, log_level="error")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(3)

        max_retries = 15
        for i in range(max_retries):
            try:
                response = httpx.get("http://localhost:8080/docs", timeout=10.0)
                if response.status_code == 200:
                    time.sleep(1)
                    break
            except (httpx.ConnectTimeout, httpx.ReadTimeout):
                time.sleep(1.5)
                if i == max_retries - 1:
                    pytest.skip("Could not start FastAPI server after multiple retries")
            except Exception as e:
                time.sleep(1)
                if i == max_retries - 1:
                    pytest.skip(f"Could not start FastAPI server: {e}")

        yield server_thread

    @pytest.fixture(scope="class")
    def fastapi_server_without_drop(self, agency_factory):
        """Start FastAPI server with drop_base64_messages disabled."""
        import threading

        from agency_swarm import run_fastapi

        app = run_fastapi(
            agencies={"test_agency": agency_factory},
            port=8082,
            app_token_env="",
            return_app=True,
            enable_agui=False,
            drop_base64_messages=False,
        )

        def run_server():
            uvicorn.run(app, host="127.0.0.1", port=8082, log_level="error")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(3)

        max_retries = 15
        for i in range(max_retries):
            try:
                response = httpx.get("http://localhost:8082/docs", timeout=10.0)
                if response.status_code == 200:
                    time.sleep(1)
                    break
            except (httpx.ConnectTimeout, httpx.ReadTimeout):
                time.sleep(1.5)
                if i == max_retries - 1:
                    pytest.skip("Could not start FastAPI server after multiple retries")
            except Exception as e:
                time.sleep(1)
                if i == max_retries - 1:
                    pytest.skip(f"Could not start FastAPI server: {e}")

        yield server_thread

    @pytest.mark.asyncio
    async def test_drop_base64_messages_enabled(self, fastapi_server_with_drop_enabled):
        """Test that tool calls and outputs with base64 data are removed when drop_base64_messages=True."""
        url = "http://localhost:8080/test_agency/get_response"

        async with self.get_http_client(timeout_seconds=120) as client:
            # First request: load the image
            payload = {
                "message": "Load the test image",
            }
            response = await client.post(url, json=payload)

            assert response.status_code == 200
            response_data = response.json()

            # Verify response contains new_messages
            assert "new_messages" in response_data
            messages = response_data["new_messages"]

            # Verify that no function_call messages with LoadTestImage are present
            function_call_messages = [
                msg for msg in messages if msg.get("type") == "function_call" and msg.get("name") == "LoadTestImage"
            ]
            assert len(function_call_messages) == 0, (
                "Function call messages should be removed when drop_base64_messages=True"
            )

            # Verify that no function_call_output messages with base64 data are present
            function_call_output_messages = [
                msg for msg in messages if msg.get("type") == "function_call_output" and _has_base64_in_output(msg)
            ]
            assert len(function_call_output_messages) == 0, (
                "Function call output messages with base64 data should be removed when drop_base64_messages=True"
            )

            # Second request: follow-up message with chat_history from first request
            followup_payload = {
                "message": "hi",
                "chat_history": messages,
            }
            followup_response = await client.post(url, json=followup_payload)

            assert followup_response.status_code == 200
            followup_response_data = followup_response.json()

            # Verify that base64 messages remain filtered in the follow-up response
            assert "new_messages" in followup_response_data
            followup_messages = followup_response_data["new_messages"]

            # Verify that no function_call messages with LoadTestImage are present in follow-up
            followup_function_call_messages = [
                msg
                for msg in followup_messages
                if msg.get("type") == "function_call" and msg.get("name") == "LoadTestImage"
            ]
            assert len(followup_function_call_messages) == 0, (
                "Function call messages should remain filtered in follow-up requests when drop_base64_messages=True"
            )

            # Verify that no function_call_output messages with base64 data are present in follow-up
            followup_function_call_output_messages = [
                msg
                for msg in followup_messages
                if msg.get("type") == "function_call_output" and _has_base64_in_output(msg)
            ]
            assert len(followup_function_call_output_messages) == 0, (
                "Function call output messages with base64 data should remain filtered "
                "in follow-up requests when drop_base64_messages=True"
            )

    @pytest.mark.asyncio
    async def test_drop_base64_messages_streaming(self, fastapi_server_with_drop_enabled):
        """Test that tool calls and outputs with base64 data are removed in streaming responses."""
        url = "http://localhost:8080/test_agency/get_response_stream"

        async with self.get_http_client(timeout_seconds=120) as client:
            # First request: load the image
            payload = {
                "message": "Load the test image",
            }

            collected_messages = []
            async with client.stream("POST", url, json=payload) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.strip() and line.startswith("event: messages"):
                        # Extract the messages from the SSE event
                        import json

                        data_part = line.split("data: ", 1)[1] if "data: " in line else None
                        if data_part:
                            try:
                                event_data = json.loads(data_part)
                                if "new_messages" in event_data:
                                    collected_messages.extend(event_data["new_messages"])
                            except json.JSONDecodeError:
                                pass

            # Verify that no function_call messages with LoadTestImage are present
            function_call_messages = [
                msg
                for msg in collected_messages
                if msg.get("type") == "function_call" and msg.get("name") == "LoadTestImage"
            ]
            assert len(function_call_messages) == 0, (
                "Function call messages should be removed in streaming when drop_base64_messages=True"
            )

            # Verify that no function_call_output messages with base64 data are present
            function_call_output_messages = [
                msg
                for msg in collected_messages
                if msg.get("type") == "function_call_output" and _has_base64_in_output(msg)
            ]
            assert len(function_call_output_messages) == 0, (
                "Function call output messages with base64 data should be removed "
                "in streaming when drop_base64_messages=True"
            )

            # Second request: follow-up message with chat_history from first request
            followup_payload = {
                "message": "hi",
                "chat_history": collected_messages,
            }

            followup_collected_messages = []
            async with client.stream("POST", url, json=followup_payload) as followup_response:
                assert followup_response.status_code == 200
                async for line in followup_response.aiter_lines():
                    if line.strip() and line.startswith("event: messages"):
                        # Extract the messages from the SSE event
                        import json

                        data_part = line.split("data: ", 1)[1] if "data: " in line else None
                        if data_part:
                            try:
                                event_data = json.loads(data_part)
                                if "new_messages" in event_data:
                                    followup_collected_messages.extend(event_data["new_messages"])
                            except json.JSONDecodeError:
                                pass

            # Verify that base64 messages remain filtered in the follow-up streaming response
            followup_function_call_messages = [
                msg
                for msg in followup_collected_messages
                if msg.get("type") == "function_call" and msg.get("name") == "LoadTestImage"
            ]
            assert len(followup_function_call_messages) == 0, (
                "Function call messages should remain filtered in follow-up streaming requests "
                "when drop_base64_messages=True"
            )

            # Verify that no function_call_output messages with base64 data are present in follow-up
            followup_function_call_output_messages = [
                msg
                for msg in followup_collected_messages
                if msg.get("type") == "function_call_output" and _has_base64_in_output(msg)
            ]
            assert len(followup_function_call_output_messages) == 0, (
                "Function call output messages with base64 data should remain filtered "
                "in follow-up streaming requests when drop_base64_messages=True"
            )


def _has_base64_in_output(msg: dict) -> bool:
    """Check if a message contains base64 data in its output."""
    if not isinstance(msg, dict):
        return False

    output = msg.get("output", [])
    if not isinstance(output, list):
        return False

    for item in output:
        if isinstance(item, dict):
            # Check for image_url with base64 data
            image_url = item.get("image_url", "")
            if isinstance(image_url, str) and image_url.startswith("data:"):
                return True
            # Check for file_data with base64 data
            file_data = item.get("file_data", "")
            if isinstance(file_data, str) and file_data.startswith("data:"):
                return True

    return False
