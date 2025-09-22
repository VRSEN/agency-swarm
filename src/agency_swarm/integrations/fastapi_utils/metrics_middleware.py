"""
Metrics collection middleware for FastAPI integration.

This middleware automatically collects performance metrics for all requests
including response times, status codes, and error rates.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .monitoring_endpoints import metrics_collector
from .production_logging import get_production_logger

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that collects performance metrics for all requests.

    Tracks:
    - Request count
    - Response times
    - Status codes
    - Error rates
    """

    def __init__(self, app: Any, exclude_paths: list[str] | None = None):
        super().__init__(app)
        # Exclude monitoring endpoints from metrics to avoid recursion
        self.exclude_paths = exclude_paths or ["/health", "/ready", "/metrics"]

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Process request and collect metrics."""
        # Skip metrics collection for monitoring endpoints
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Record start time
        start_time = time.time()

        try:
            # Process the request
            response = await call_next(request)

            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000

            # Record metrics
            metrics_collector.record_request(response_time_ms, response.status_code)

            # Log request with production logger if available
            prod_logger = get_production_logger()
            if prod_logger:
                client_ip = request.client.host if request.client else "unknown"
                user_agent = request.headers.get("user-agent", "unknown")
                prod_logger.log_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    response_time_ms=response_time_ms,
                    client_ip=client_ip,
                    user_agent=user_agent,
                )

            # Add performance headers
            response.headers["X-Response-Time"] = f"{response_time_ms:.2f}ms"

            return response

        except Exception as e:
            # Record error metrics
            response_time_ms = (time.time() - start_time) * 1000
            metrics_collector.record_request(response_time_ms, 500)

            # Log error with production logger if available
            prod_logger = get_production_logger()
            if prod_logger:
                client_ip = request.client.host if request.client else "unknown"
                prod_logger.log_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    response_time_ms=response_time_ms,
                    client_ip=client_ip,
                )

            logger.error(f"Request failed: {e}")
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Adds headers for:
    - Content Security Policy
    - X-Frame-Options
    - X-Content-Type-Options
    - X-XSS-Protection
    - Strict-Transport-Security
    """

    def __init__(self, app: Any):
        super().__init__(app)
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
            # Add HSTS only in production with HTTPS
            # "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
        }

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Add security headers to response."""
        response = await call_next(request)

        # Add security headers
        for header, value in self.security_headers.items():
            response.headers[header] = value

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware.

    Implements a basic token bucket algorithm for rate limiting.
    """

    def __init__(self, app: Any, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_minute / 60.0
        self.client_buckets: dict[str, tuple[float, float]] = {}  # client_ip -> (tokens, last_update)
        self.bucket_capacity = requests_per_minute

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded headers first (for load balancers/proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct client IP
        return request.client.host if request.client else "unknown"

    def _update_bucket(self, client_ip: str) -> bool:
        """
        Update token bucket for client and return True if request is allowed.
        """
        current_time = time.time()

        if client_ip not in self.client_buckets:
            # New client, give them a full bucket
            self.client_buckets[client_ip] = (self.bucket_capacity - 1, current_time)
            return True

        tokens, last_update = self.client_buckets[client_ip]

        # Add tokens based on time elapsed
        time_elapsed = current_time - last_update
        tokens_to_add = time_elapsed * self.requests_per_second
        tokens = min(self.bucket_capacity, tokens + tokens_to_add)

        if tokens >= 1:
            # Allow request and consume token
            self.client_buckets[client_ip] = (tokens - 1, current_time)
            return True
        else:
            # Rate limit exceeded
            self.client_buckets[client_ip] = (tokens, current_time)
            return False

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Check rate limit and process request."""
        # Skip rate limiting for monitoring endpoints
        if request.url.path in ["/health", "/ready", "/metrics"]:
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        if not self._update_bucket(client_ip):
            # Rate limit exceeded
            logger.warning(f"Rate limit exceeded for client {client_ip}")
            return Response(
                content="Rate limit exceeded. Please try again later.",
                status_code=429,
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Process request normally
        response = await call_next(request)

        # Add rate limit headers
        tokens, _ = self.client_buckets.get(client_ip, (0, 0))
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(int(tokens))

        return response
