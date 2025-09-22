"""
Health check and monitoring utilities for FastAPI integration.

This module provides comprehensive health checking capabilities including:
- Service availability and response time monitoring
- OpenAI API connectivity verification
- Resource usage monitoring (CPU, memory)
- External dependency health checks
"""

import asyncio
import logging
import os
import time
from typing import Any, Optional

import httpx
import psutil

logger = logging.getLogger(__name__)


class HealthCheckResult:
    """Represents the result of a health check operation."""
    
    def __init__(
        self,
        name: str,
        status: str,
        message: str = "",
        duration_ms: float = 0.0,
        details: dict[str, Any] | None = None,
    ):
        self.name = name
        self.status = status  # "healthy", "unhealthy", "degraded"
        self.message = message
        self.duration_ms = duration_ms
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "details": self.details
        }


class HealthChecker:
    """Comprehensive health checking system for production monitoring."""

    def __init__(self):
        self.checks: list[callable] = []
        self.timeout_seconds = 10.0

    def add_check(self, check_func: callable) -> None:
        """Add a health check function."""
        self.checks.append(check_func)

    async def run_all_checks(self) -> dict[str, Any]:
        """Run all registered health checks and return comprehensive status."""
        start_time = time.time()
        results = []
        overall_status = "healthy"
        
        for check_func in self.checks:
            try:
                result = await asyncio.wait_for(check_func(), timeout=self.timeout_seconds)
                results.append(result)
                
                if result.status == "unhealthy":
                    overall_status = "unhealthy"
                elif result.status == "degraded" and overall_status == "healthy":
                    overall_status = "degraded"
                    
            except TimeoutError:
                result = HealthCheckResult(
                    name=check_func.__name__,
                    status="unhealthy",
                    message=f"Health check timed out after {self.timeout_seconds}s"
                )
                results.append(result)
                overall_status = "unhealthy"
            except Exception as e:
                result = HealthCheckResult(
                    name=check_func.__name__,
                    status="unhealthy",
                    message=f"Health check failed: {str(e)}"
                )
                results.append(result)
                overall_status = "unhealthy"
        
        total_duration = (time.time() - start_time) * 1000
        
        return {
            "status": overall_status,
            "timestamp": time.time(),
            "duration_ms": round(total_duration, 2),
            "checks": [result.to_dict() for result in results],
            "summary": {
                "total_checks": len(results),
                "healthy": len([r for r in results if r.status == "healthy"]),
                "degraded": len([r for r in results if r.status == "degraded"]),
                "unhealthy": len([r for r in results if r.status == "unhealthy"])
            }
        }


# Health check implementations
async def check_basic_service() -> HealthCheckResult:
    """Basic service availability check."""
    start_time = time.time()
    
    try:
        # Simple service availability test
        duration_ms = (time.time() - start_time) * 1000
        
        return HealthCheckResult(
            name="basic_service",
            status="healthy",
            message="Service is responding",
            duration_ms=duration_ms
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="basic_service",
            status="unhealthy",
            message=f"Service check failed: {str(e)}",
            duration_ms=duration_ms
        )


async def check_openai_api() -> HealthCheckResult:
    """Check OpenAI API connectivity and authentication."""
    start_time = time.time()
    
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return HealthCheckResult(
                name="openai_api",
                status="unhealthy",
                message="OPENAI_API_KEY not configured",
                duration_ms=(time.time() - start_time) * 1000
            )
        
        # Test OpenAI API connectivity with a minimal request
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                return HealthCheckResult(
                    name="openai_api",
                    status="healthy",
                    message="OpenAI API is accessible",
                    duration_ms=duration_ms,
                    details={"response_code": response.status_code}
                )
            elif response.status_code == 401:
                return HealthCheckResult(
                    name="openai_api",
                    status="unhealthy",
                    message="OpenAI API authentication failed",
                    duration_ms=duration_ms,
                    details={"response_code": response.status_code}
                )
            else:
                return HealthCheckResult(
                    name="openai_api",
                    status="degraded",
                    message=f"OpenAI API returned status {response.status_code}",
                    duration_ms=duration_ms,
                    details={"response_code": response.status_code}
                )
                
    except httpx.TimeoutException:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="openai_api",
            status="degraded",
            message="OpenAI API request timed out",
            duration_ms=duration_ms
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="openai_api",
            status="unhealthy",
            message=f"OpenAI API check failed: {str(e)}",
            duration_ms=duration_ms
        )


async def check_system_resources() -> HealthCheckResult:
    """Check system resource usage (CPU, memory, disk)."""
    start_time = time.time()
    
    try:
        # Get system resource usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Define thresholds
        cpu_warning_threshold = 80.0
        cpu_critical_threshold = 95.0
        memory_warning_threshold = 80.0
        memory_critical_threshold = 95.0
        disk_warning_threshold = 85.0
        disk_critical_threshold = 95.0
        
        status = "healthy"
        messages = []
        
        # Check CPU usage
        if cpu_percent > cpu_critical_threshold:
            status = "unhealthy"
            messages.append(f"Critical CPU usage: {cpu_percent:.1f}%")
        elif cpu_percent > cpu_warning_threshold:
            if status == "healthy":
                status = "degraded"
            messages.append(f"High CPU usage: {cpu_percent:.1f}%")
        
        # Check memory usage
        if memory.percent > memory_critical_threshold:
            status = "unhealthy"
            messages.append(f"Critical memory usage: {memory.percent:.1f}%")
        elif memory.percent > memory_warning_threshold:
            if status == "healthy":
                status = "degraded"
            messages.append(f"High memory usage: {memory.percent:.1f}%")
        
        # Check disk usage
        if disk.percent > disk_critical_threshold:
            status = "unhealthy"
            messages.append(f"Critical disk usage: {disk.percent:.1f}%")
        elif disk.percent > disk_warning_threshold:
            if status == "healthy":
                status = "degraded"
            messages.append(f"High disk usage: {disk.percent:.1f}%")
        
        message = "; ".join(messages) if messages else "System resources within normal limits"
        
        return HealthCheckResult(
            name="system_resources",
            status=status,
            message=message,
            duration_ms=duration_ms,
            details={
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory.percent, 1),
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": round(disk.percent, 1),
                "disk_free_gb": round(disk.free / (1024**3), 2)
            }
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="system_resources",
            status="unhealthy",
            message=f"Resource check failed: {str(e)}",
            duration_ms=duration_ms
        )


# Global health checker instance
health_checker = HealthChecker()

# Register default health checks
health_checker.add_check(check_basic_service)
health_checker.add_check(check_openai_api)
health_checker.add_check(check_system_resources)
