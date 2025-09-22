"""
Integration test for FastAPI file processing functionality.

This test verifies that the FastAPI endpoints can properly handle file_urls parameter,
process various file types through HTTP requests, and return appropriate responses
containing the expected file content.
"""

import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


class TestFastAPIFileProcessing:
    """Test suite for FastAPI file processing with file_urls parameter."""

    @staticmethod
    def get_http_client(timeout_seconds: int = 60) -> httpx.AsyncClient:
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
                and provide detailed information about what you find. Always include any secret phrases
                or specific content mentioned in the files.
                """,
                description="Agent that processes and analyzes file content",
                model="gpt-4.1",
                model_settings=ModelSettings(
                    temperature=0,
                ),
            )

            return Agency(
                agent,
                load_threads_callback=load_threads_callback,
                save_threads_callback=save_threads_callback,
            )

        return create_agency

    @pytest.fixture(scope="class")
    def file_server_process(self):
        """Start HTTP file server on port 7860 for serving test files."""
        # Get the path to tests/data/files directory
        test_files_dir = Path(__file__).parent.parent / "data" / "files"
        if not test_files_dir.exists():
            pytest.skip(f"Test files directory not found: {test_files_dir}")

        # Start HTTP server
        server_process = subprocess.Popen(
            [sys.executable, "-m", "http.server", "7860"],
            cwd=test_files_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to start
        time.sleep(2)

        # Verify server is running
        try:
            response = httpx.get("http://localhost:7860/", timeout=5)
            assert response.status_code == 200
        except Exception as e:
            server_process.terminate()
            pytest.skip(f"Could not start file server: {e}")

        yield server_process

        # Cleanup
        server_process.terminate()
        server_process.wait()

    @pytest.fixture(scope="class")
    def fastapi_server(self, agency_factory):
        """Create FastAPI app for testing."""
        from agency_swarm import run_fastapi

        # Create app without starting server - we'll use TestClient
        app = run_fastapi(
            agencies={"test_agency": agency_factory}, app_token_env="", return_app=True, enable_agui=False
        )

        yield app

    def test_file_search_attachment(self, file_server_process, fastapi_server):
        """Test processing a single text file via file_urls."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_server)
        payload = {
            "message": "Please read the content of the uploaded file and tell me what secret phrase you find.",
            "file_urls": {"test_file.txt": "http://localhost:7860/test-txt.txt"},
        }

        response = client.post("/test_agency/get_response", json=payload)

        assert response.status_code == 200
        response_data = response.json()

        # Verify response contains expected content
        assert "response" in response_data
        response_text = response_data["response"].lower()
        assert "first txt secret phrase" in response_text

    def test_code_interpreter_attachment(self, file_server_process, fastapi_server):
        """Test processing an HTML file via file_urls."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_server)
        payload = {
            "message": "Search for the secret phrase inside the document.",
            "file_urls": {"webpage.html": "http://localhost:7860/test-html.html"},
        }

        response = client.post("/test_agency/get_response", json=payload)

        assert response.status_code == 200
        response_data = response.json()

        response_text = response_data["response"].lower()
        # Should find both secret phrases in HTML
        assert "first html secret phrase" in response_text or "second html secret phrase" in response_text

        file_ids = response_data["file_ids_map"]
        assert "webpage.html" in file_ids.keys()

    def test_image_and_pdf_attachments(self, file_server_process, fastapi_server):
        """Test processing multiple files simultaneously via file_urls."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_server)
        payload = {
            "message": (
                "I'm uploading multiple files. Please tell me the function name presented in the image"
                "and tell me the contents of the pdf file"
            ),
            "file_urls": {
                "text_image": "http://localhost:7860/test-image.png",
                "pdf_file": "http://localhost:7860/test-pdf.pdf",
            },
        }

        response = client.post("/test_agency/get_response", json=payload)

        assert response.status_code == 200
        response_data = response.json()

        response_text = response_data["response"].lower()
        # Should find secret phrases from multiple files
        assert "first pdf secret phrase" in response_text
        assert "sum_of_squares" in response_text or "sum of squares" in response_text

    def test_streaming_response(self, file_server_process, fastapi_server):
        """Test streaming response with file processing."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_server)
        payload = {
            "message": "Please read the text file and describe its content in detail.",
            "file_urls": {"stream_test.txt": "http://localhost:7860/test-txt.txt"},
        }

        with client.stream("POST", "/test_agency/get_response_stream", json=payload) as response:
            assert response.status_code == 200
            collected_data = []
            for line in response.iter_lines():
                if line.strip():
                    collected_data.append(line)

        # Verify we received streaming data
        assert len(collected_data) > 0

        # Join all collected data to check for content
        full_response = " ".join(collected_data).lower()
        assert "first txt secret phrase" in full_response

    def test_invalid_file_url(self, file_server_process, fastapi_server):
        """Test handling of invalid file URLs."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_server)
        payload = {
            "message": "Please process this file.",
            "file_urls": {"nonexistent.txt": "http://localhost:7860/nonexistent-file.txt"},
        }

        response = client.post("/test_agency/get_response", json=payload)

        # The request should return 400 for file download errors
        assert response.status_code == 400
        response_data = response.json()

        # The error should mention it couldn't access the file
        response_text = response_data["error"].lower()
        assert "error downloading file from provided urls" in response_text

    def test_streaming_invalid_file_url(self, file_server_process, fastapi_server):
        """Test that streaming endpoint properly handles invalid file URLs without hanging."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_server)
        payload = {
            "message": "Please process this file.",
            "file_urls": {"nonexistent.txt": "http://localhost:7860/nonexistent-file.txt"},
        }

        collected_data = []
        error_found = False

        with client.stream("POST", "/test_agency/get_response_stream", json=payload) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
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
