"""
Monitoring and health check endpoints for FastAPI integration.

This module provides production-ready monitoring endpoints including:
- /health - Basic health check for load balancers
- /ready - Readiness check for Kubernetes
- /metrics - Performance metrics endpoint
"""

import logging
import time
from typing import Any

from fastapi.responses import JSONResponse

from .health_check import health_checker

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and stores performance metrics."""

    def __init__(self) -> None:
        self.request_count = 0
        self.error_count = 0
        self.response_times: list[float] = []
        self.start_time = time.time()
        self.last_reset = time.time()

    def record_request(self, response_time_ms: float, status_code: int) -> None:
        """Record a request with its response time and status code."""
        self.request_count += 1
        self.response_times.append(response_time_ms)

        if status_code >= 400:
            self.error_count += 1

        # Keep only last 1000 response times to prevent memory growth
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-1000:]

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics summary."""
        uptime_seconds = time.time() - self.start_time

        if not self.response_times:
            return {
                "uptime_seconds": round(uptime_seconds, 2),
                "request_count": self.request_count,
                "error_count": self.error_count,
                "error_rate": 0.0,
                "requests_per_second": 0.0,
                "response_times": {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0},
            }

        # Calculate percentiles
        sorted_times = sorted(self.response_times)
        count = len(sorted_times)

        p50_idx = int(count * 0.5)
        p95_idx = int(count * 0.95)
        p99_idx = int(count * 0.99)

        p50 = sorted_times[p50_idx] if p50_idx < count else sorted_times[-1]
        p95 = sorted_times[p95_idx] if p95_idx < count else sorted_times[-1]
        p99 = sorted_times[p99_idx] if p99_idx < count else sorted_times[-1]
        avg = sum(self.response_times) / len(self.response_times)

        # Calculate requests per second
        time_window = time.time() - self.last_reset
        rps = self.request_count / time_window if time_window > 0 else 0

        # Calculate error rate
        error_rate = (self.error_count / self.request_count * 100) if self.request_count > 0 else 0

        return {
            "uptime_seconds": round(uptime_seconds, 2),
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": round(error_rate, 2),
            "requests_per_second": round(rps, 2),
            "response_times": {
                "count": count,
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2),
                "avg": round(avg, 2),
            },
        }

    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        self.request_count = 0
        self.error_count = 0
        self.response_times = []
        self.last_reset = time.time()


# Global metrics collector
metrics_collector = MetricsCollector()


async def health_endpoint() -> JSONResponse:
    """
    Basic health check endpoint for load balancers.

    Returns:
        200: Service is healthy
        503: Service is unhealthy
    """
    try:
        health_result = await health_checker.run_all_checks()

        if health_result["status"] == "healthy":
            return JSONResponse(
                status_code=200,
                content={"status": "healthy", "timestamp": health_result["timestamp"], "version": "1.0.2"},
            )
        elif health_result["status"] == "degraded":
            return JSONResponse(
                status_code=200,
                content={
                    "status": "degraded",
                    "timestamp": health_result["timestamp"],
                    "version": "1.0.2",
                    "warnings": [
                        check["message"] for check in health_result["checks"] if check["status"] == "degraded"
                    ],
                },
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "timestamp": health_result["timestamp"],
                    "version": "1.0.2",
                    "errors": [check["message"] for check in health_result["checks"] if check["status"] == "unhealthy"],
                },
            )

    except Exception as e:
        logger.error(f"Health check endpoint failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": time.time(),
                "version": "1.0.2",
                "error": "Health check system failure",
            },
        )


async def readiness_endpoint() -> JSONResponse:
    """
    Readiness check endpoint for Kubernetes.

    Returns detailed health information including all checks.

    Returns:
        200: Service is ready to receive traffic
        503: Service is not ready
    """
    try:
        health_result = await health_checker.run_all_checks()

        if health_result["status"] in ["healthy", "degraded"]:
            return JSONResponse(
                status_code=200,
                content={
                    "ready": True,
                    "status": health_result["status"],
                    "timestamp": health_result["timestamp"],
                    "duration_ms": health_result["duration_ms"],
                    "checks": health_result["checks"],
                    "summary": health_result["summary"],
                },
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "status": health_result["status"],
                    "timestamp": health_result["timestamp"],
                    "duration_ms": health_result["duration_ms"],
                    "checks": health_result["checks"],
                    "summary": health_result["summary"],
                },
            )

    except Exception as e:
        logger.error(f"Readiness check endpoint failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "status": "unhealthy",
                "timestamp": time.time(),
                "error": "Readiness check system failure",
            },
        )


async def metrics_endpoint() -> JSONResponse:
    """
    Performance metrics endpoint.

    Returns current performance metrics including response times,
    request counts, error rates, and system resource usage.
    """
    try:
        # Get performance metrics
        performance_metrics = metrics_collector.get_metrics()

        # Get current health status
        health_result = await health_checker.run_all_checks()

        return JSONResponse(
            status_code=200,
            content={
                "timestamp": time.time(),
                "service": {"status": health_result["status"], "version": "1.0.2"},
                "performance": performance_metrics,
                "health_checks": {"duration_ms": health_result["duration_ms"], "summary": health_result["summary"]},
            },
        )

    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return JSONResponse(status_code=500, content={"timestamp": time.time(), "error": "Metrics collection failure"})


def create_monitoring_endpoints() -> dict[str, Any]:
    """
    Create monitoring endpoint handlers.

    Returns:
        Dictionary of endpoint paths and their handlers
    """
    return {"/health": health_endpoint, "/ready": readiness_endpoint, "/metrics": metrics_endpoint}
