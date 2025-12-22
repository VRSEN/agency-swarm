"""
Integration test for FastAPI file processing functionality.

This test verifies that the FastAPI endpoints can properly handle file_urls parameter,
process various file types through HTTP requests, and return appropriate responses
containing the expected file content.
"""

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from agents import ModelSettings
from openai.types.shared import Reasoning

from agency_swarm import Agency, Agent, run_fastapi


class TestFastAPIFileProcessing:
    """Test suite for FastAPI file processing with file_urls parameter."""

    @staticmethod
    def _get_free_tcp_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def get_http_client(timeout_seconds: int = 120) -> httpx.AsyncClient:
        """Create an HTTP client with proper timeout configuration."""
        timeout_config = httpx.Timeout(
            timeout_seconds,  # Total timeout (first positional arg)
            connect=10.0,  # Connection timeout
            read=timeout_seconds,  # Read timeout for the entire response
            write=10.0,  # Write timeout for sending request
            pool=5.0,  # Pool connection timeout
        )
        return httpx.AsyncClient(timeout=timeout_config)

    @pytest.fixture(scope="class")
    def agency_factory(self):
        """Create an agency factory for testing."""

        def create_agency(load_threads_callback=None, save_threads_callback=None):
            agent = Agent(
                name="FileProcessorAgent",
                instructions="""
                You are a file processing agent. When you receive files, read their content carefully
                and echo back the exact secret phrases found in the files verbatim—do not paraphrase or invent
                alternative text. If multiple phrases appear, include them all exactly as written.
                """,
                description="Agent that processes and analyzes file content",
                model="gpt-5.1",
                model_settings=ModelSettings(
                    reasoning=Reasoning(effort="low"),
                ),
            )

            return Agency(
                agent,
                load_threads_callback=load_threads_callback,
                save_threads_callback=save_threads_callback,
            )

        return create_agency

    @pytest.fixture(scope="class")
    def file_server_base_url(self) -> str:
        """Start HTTP file server for serving test files."""
        # Get the path to tests/data/files directory
        test_files_dir = Path(__file__).parents[2] / "data" / "files"
        if not test_files_dir.exists():
            pytest.skip(f"Test files directory not found: {test_files_dir}")

        port = self._get_free_tcp_port()
        base_url = f"http://127.0.0.1:{port}"

        # Start HTTP server
        server_process = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=test_files_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for server to start
        time.sleep(2)

        # Verify server is running
        try:
            response = httpx.get(f"{base_url}/", timeout=5)
            assert response.status_code == 200
        except Exception as e:
            server_process.terminate()
            pytest.skip(f"Could not start file server: {e}")

        yield base_url

        # Cleanup
        server_process.terminate()
        server_process.wait()

    @pytest.fixture(scope="class")
    def fastapi_base_url(self, agency_factory) -> str:
        """Start FastAPI server on an available port."""
        port = self._get_free_tcp_port()
        base_url = f"http://127.0.0.1:{port}"

        # Ensure no authentication is required by using a non-existent env var
        # This will make app_token None and disable authentication
        app = run_fastapi(
            agencies={"test_agency": agency_factory}, port=port, app_token_env="", return_app=True, enable_agui=False
        )

        # Start server in a thread
        def run_server():
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(3)

        # Verify server is running with proper timeout configuration
        max_retries = 15
        for i in range(max_retries):
            try:
                response = httpx.get(f"{base_url}/docs", timeout=10.0)
                if response.status_code == 200:
                    # Ensure server is fully ready
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

        yield base_url

    @pytest.mark.asyncio
    async def test_chat_name(self, file_server_base_url: str, fastapi_base_url: str):
        """Test processing a single text file via file_urls with chat name generation."""
        url = f"{fastapi_base_url}/test_agency/get_response"
        payload = {
            "message": "I want to find a restaurant in New York.",
            "generate_chat_name": True,
        }
        async with self.get_http_client(timeout_seconds=20) as client:
            response = await client.post(url, json=payload)
        assert response.status_code == 200
        response_data = response.json()
        assert "chat_name" in response_data
        assert len(response_data["chat_name"]) > 0

    @pytest.mark.asyncio
    async def test_file_search_attachment(self, file_server_base_url: str, fastapi_base_url: str):
        """Test processing a single text file via file_urls."""
        url = f"{fastapi_base_url}/test_agency/get_response"
        payload = {
            "message": "Please read the content of the uploaded file and tell me what secret phrase you find.",
            "file_urls": {"test_file.txt": f"{file_server_base_url}/test-txt.txt"},
        }
        headers = {}

        async with self.get_http_client(timeout_seconds=120) as client:
            response = await client.post(url, json=payload, headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        # Verify response contains expected content
        assert "response" in response_data
        response_text = response_data["response"].lower()
        assert "first txt secret phrase" in response_text

    @pytest.mark.asyncio
    async def test_code_interpreter_attachment(self, file_server_base_url: str, fastapi_base_url: str):
        """Test processing an HTML file via file_urls."""
        url = f"{fastapi_base_url}/test_agency/get_response"
        payload = {
            "message": "Search for the secret phrase inside the document.",
            "file_urls": {"webpage.html": f"{file_server_base_url}/test-html.html"},
        }
        headers = {}

        async with self.get_http_client(timeout_seconds=120) as client:
            response = await client.post(url, json=payload, headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        response_text = response_data["response"].lower()
        # Should find both secret phrases in HTML
        assert "first html secret phrase" in response_text or "second html secret phrase" in response_text

        file_ids = response_data["file_ids_map"]
        assert "webpage.html" in file_ids.keys()

    @pytest.mark.asyncio
    async def test_image_and_pdf_attachments(self, file_server_base_url: str, fastapi_base_url: str):
        """Test processing multiple files simultaneously via file_urls."""
        url = f"{fastapi_base_url}/test_agency/get_response"
        payload = {
            "message": (
                "I'm uploading multiple files. Please tell me the function name presented in the image"
                "and tell me what my favorite food is."
            ),
            "file_urls": {
                "text_image": f"{file_server_base_url}/test-image.png",
                "pdf_file": f"{file_server_base_url}/test-pdf-2.pdf",
            },
        }
        headers = {}

        async with self.get_http_client(timeout_seconds=120) as client:
            response = await client.post(url, json=payload, headers=headers)

        assert response.status_code == 200
        response_data = response.json()

        response_text = response_data["response"].lower()
        # Should find secret phrases from multiple files
        assert "strawberry" in response_text.lower()
        assert "sum_of_squares" in response_text or "sum of squares" in response_text

    @pytest.mark.asyncio
    async def test_streaming_response(self, file_server_base_url: str, fastapi_base_url: str):
        """Test streaming response with file processing."""
        url = f"{fastapi_base_url}/test_agency/get_response_stream"
        payload = {
            "message": "Please read the text file and describe its content in detail.",
            "file_urls": {"stream_test.txt": f"{file_server_base_url}/test-txt.txt"},
        }
        headers = {}

        collected_data = []
        async with self.get_http_client(timeout_seconds=120) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.strip():
                        collected_data.append(line)

        # Verify we received streaming data
        assert len(collected_data) > 0

        # Join all collected data to check for content
        full_response = " ".join(collected_data).lower()
        assert "first txt secret phrase" in full_response

    @pytest.mark.asyncio
    async def test_invalid_file_url(self, file_server_base_url: str, fastapi_base_url: str):
        """Test handling of invalid file URLs."""
        url = f"{fastapi_base_url}/test_agency/get_response"
        payload = {
            "message": "Please process this file.",
            "file_urls": {"nonexistent.txt": f"{file_server_base_url}/nonexistent-file.txt"},
        }
        headers = {}

        async with self.get_http_client(timeout_seconds=60) as client:
            response = await client.post(url, json=payload, headers=headers)

        # The request should still return 200, but the response should indicate file issues
        assert response.status_code == 200
        response_data = response.json()

        # The agent should mention it couldn't access the file
        response_text = response_data["error"].lower()
        assert "error downloading file from provided urls" in response_text

    @pytest.mark.asyncio
    async def test_streaming_invalid_file_url(self, file_server_base_url: str, fastapi_base_url: str):
        """Test that streaming endpoint properly handles invalid file URLs without hanging."""
        url = f"{fastapi_base_url}/test_agency/get_response_stream"
        payload = {
            "message": "Please process this file.",
            "file_urls": {"nonexistent.txt": f"{file_server_base_url}/nonexistent-file.txt"},
        }
        headers = {}

        collected_data = []
        error_found = False

        async with self.get_http_client(timeout_seconds=60) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.strip():
                        collected_data.append(line)
                        # Check if this is an error event
                        if line.startswith("data: "):
                            try:
                                import json

                                data = json.loads(line[6:])  # Remove "data: " prefix
                                if "error" in data:
                                    error_found = True
                                    assert "error downloading file from provided urls" in data["error"].lower()
                            except json.JSONDecodeError:
                                pass  # Some lines might not be JSON

        # Verify we received streaming data and found the error
        assert len(collected_data) > 0, "Should have received streaming data"
        assert error_found, "Should have received an error event for invalid file URL"
