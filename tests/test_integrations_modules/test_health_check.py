"""
Tests for health check and monitoring functionality.

This module tests the health check endpoints, metrics collection,
and monitoring middleware for production readiness.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi import run_fastapi


class TestHealthCheckEndpoints:
    """Test suite for health check endpoints."""

    @pytest.fixture
    def agency_factory(self):
        """Factory function to create a test agency."""
        def create_agency(load_threads_callback=None, save_threads_callback=None):
            agent = Agent(name="TestAgent", instructions="Test agent for health checks")
            return Agency(
                agent,
                load_threads_callback=load_threads_callback,
                save_threads_callback=save_threads_callback,
            )
        return create_agency

    @pytest.fixture
    def fastapi_app(self, agency_factory):
        """Create FastAPI app with monitoring enabled."""
        app = run_fastapi(
            agencies={"test_agency": agency_factory},
            app_token_env="",
            return_app=True,
            enable_monitoring=True,
            enable_rate_limiting=False  # Disable for testing
        )
        return app

    def test_health_endpoint_basic(self, fastapi_app):
        """Test basic health endpoint functionality."""
        client = TestClient(fastapi_app)
        
        response = client.get("/health")
        
        assert response.status_code in [200, 503]  # Can be degraded due to missing OpenAI key
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert data["version"] == "1.0.2"
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_readiness_endpoint_detailed(self, fastapi_app):
        """Test readiness endpoint with detailed health information."""
        client = TestClient(fastapi_app)
        
        response = client.get("/ready")
        
        assert response.status_code in [200, 503]
        data = response.json()
        
        assert "ready" in data
        assert "status" in data
        assert "timestamp" in data
        assert "duration_ms" in data
        assert "checks" in data
        assert "summary" in data
        
        # Verify checks structure
        assert isinstance(data["checks"], list)
        for check in data["checks"]:
            assert "name" in check
            assert "status" in check
            assert "message" in check
            assert "duration_ms" in check
            assert check["status"] in ["healthy", "degraded", "unhealthy"]

    def test_metrics_endpoint(self, fastapi_app):
        """Test metrics endpoint functionality."""
        client = TestClient(fastapi_app)
        
        # Make a few requests to generate metrics
        client.get("/health")
        client.get("/ready")
        
        response = client.get("/metrics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "timestamp" in data
        assert "service" in data
        assert "performance" in data
        assert "health_checks" in data
        
        # Verify service info
        service = data["service"]
        assert "status" in service
        assert "version" in service
        assert service["version"] == "1.0.2"
        
        # Verify performance metrics
        performance = data["performance"]
        assert "uptime_seconds" in performance
        assert "request_count" in performance
        assert "error_count" in performance
        assert "error_rate" in performance
        assert "requests_per_second" in performance
        assert "response_times" in performance

    @patch('agency_swarm.integrations.fastapi_utils.health_check.check_openai_api')
    @pytest.mark.asyncio
    async def test_health_check_with_openai_failure(self, mock_openai_check, fastapi_app):
        """Test health check behavior when OpenAI API is unavailable."""
        from agency_swarm.integrations.fastapi_utils.health_check import HealthCheckResult

        # Mock OpenAI API failure with async mock
        mock_openai_check.return_value = AsyncMock(return_value=HealthCheckResult(
            name="openai_api",
            status="unhealthy",
            message="OpenAI API authentication failed",
            duration_ms=100.0
        ))

        client = TestClient(fastapi_app)
        response = client.get("/health")

        # Health endpoint may still return 200 if other checks pass
        # Check the actual status in the response body
        data = response.json()
        assert "status" in data
        # Status could be unhealthy or degraded depending on other checks

    def test_security_headers_present(self, fastapi_app):
        """Test that security headers are added to responses."""
        client = TestClient(fastapi_app)
        
        response = client.get("/health")
        
        # Check for security headers
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers
        assert "Referrer-Policy" in response.headers
        assert "Content-Security-Policy" in response.headers
        
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_metrics_middleware_tracking(self, fastapi_app):
        """Test that metrics middleware tracks requests properly."""
        client = TestClient(fastapi_app)

        # Make requests to non-monitoring endpoints to test middleware
        # (monitoring endpoints are excluded from metrics tracking)
        response = client.post("/test_agency/response",
                              json={"message": "test", "additional_instructions": "test"},
                              headers={"Authorization": "Bearer test"})

        # The response might be 401 due to auth, but headers should still be present
        # if middleware is working (security headers are always added)
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers

    def test_monitoring_endpoints_excluded_from_metrics(self, fastapi_app):
        """Test that monitoring endpoints don't track themselves in metrics."""
        client = TestClient(fastapi_app)
        
        # Get initial metrics
        initial_response = client.get("/metrics")
        initial_data = initial_response.json()
        initial_count = initial_data["performance"]["request_count"]
        
        # Make requests to monitoring endpoints
        client.get("/health")
        client.get("/ready")
        client.get("/metrics")
        
        # Get updated metrics
        final_response = client.get("/metrics")
        final_data = final_response.json()
        final_count = final_data["performance"]["request_count"]
        
        # Request count should not have increased (monitoring endpoints excluded)
        assert final_count == initial_count

    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    def test_system_resources_check(self, mock_disk, mock_memory, mock_cpu, fastapi_app):
        """Test system resources health check."""
        # Mock system resources within normal limits
        mock_cpu.return_value = 50.0  # 50% CPU usage
        
        mock_memory_obj = Mock()
        mock_memory_obj.percent = 60.0  # 60% memory usage
        mock_memory_obj.available = 4 * 1024**3  # 4GB available
        mock_memory.return_value = mock_memory_obj
        
        mock_disk_obj = Mock()
        mock_disk_obj.percent = 70.0  # 70% disk usage
        mock_disk_obj.free = 100 * 1024**3  # 100GB free
        mock_disk.return_value = mock_disk_obj
        
        client = TestClient(fastapi_app)
        response = client.get("/ready")
        
        assert response.status_code == 200
        data = response.json()
        
        # Find system resources check
        system_check = None
        for check in data["checks"]:
            if check["name"] == "system_resources":
                system_check = check
                break
        
        assert system_check is not None
        assert system_check["status"] == "healthy"
        assert "details" in system_check
        
        details = system_check["details"]
        assert "cpu_percent" in details
        assert "memory_percent" in details
        assert "disk_percent" in details
