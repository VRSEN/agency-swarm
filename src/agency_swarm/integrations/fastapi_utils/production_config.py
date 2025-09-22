"""
Production configuration and environment management for Agency Swarm.

This module provides production-ready configuration management including:
- Environment variable validation
- Security settings
- Performance tuning
- Deployment configuration
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SecurityConfig:
    """Security configuration for production deployment."""

    # Authentication
    require_auth_token: bool = True
    auth_token_env: str = "APP_TOKEN"

    # CORS settings
    cors_origins: list[str] = field(default_factory=lambda: ["https://yourdomain.com"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = field(default_factory=lambda: ["GET", "POST"])
    cors_allow_headers: list[str] = field(default_factory=lambda: ["*"])

    # Security headers
    enable_security_headers: bool = True
    content_security_policy: str = "default-src 'self'"

    # Rate limiting
    enable_rate_limiting: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10

    # HTTPS settings
    force_https: bool = True
    hsts_max_age: int = 31536000  # 1 year

    def validate(self) -> list[str]:
        """Validate security configuration and return any issues."""
        issues = []

        if self.require_auth_token and not os.getenv(self.auth_token_env):
            issues.append(f"Authentication token not set in {self.auth_token_env}")

        if not self.cors_origins or "*" in self.cors_origins:
            issues.append("CORS origins should be restricted in production")

        if self.rate_limit_per_minute < 10:
            issues.append("Rate limit may be too restrictive for production")

        return issues


@dataclass
class PerformanceConfig:
    """Performance configuration for production deployment."""

    # Server settings
    workers: int = 4
    max_connections: int = 1000
    keepalive_timeout: int = 5

    # Request limits
    max_request_size_mb: int = 100
    request_timeout_seconds: int = 300

    # Monitoring
    enable_monitoring: bool = True
    metrics_retention_hours: int = 24
    health_check_interval_seconds: int = 30

    # Logging
    log_level: str = "INFO"
    log_retention_days: int = 30
    max_log_file_size_mb: int = 100

    # OpenAI API settings
    openai_timeout_seconds: int = 60
    openai_max_retries: int = 3
    openai_backoff_factor: float = 2.0

    def validate(self) -> list[str]:
        """Validate performance configuration and return any issues."""
        issues = []

        if self.workers < 1:
            issues.append("At least 1 worker is required")

        if self.max_connections < 100:
            issues.append("Max connections may be too low for production")

        if self.request_timeout_seconds < 30:
            issues.append("Request timeout may be too short")

        return issues


@dataclass
class DeploymentConfig:
    """Deployment configuration for production environment."""

    # Environment
    environment: str = "production"
    debug: bool = False

    # Server binding
    host: str = "0.0.0.0"
    port: int = 8000

    # SSL/TLS
    ssl_keyfile: str | None = None
    ssl_certfile: str | None = None

    # Health checks
    health_check_path: str = "/health"
    readiness_check_path: str = "/ready"

    # Graceful shutdown
    graceful_shutdown_timeout: int = 30

    # External dependencies
    required_env_vars: list[str] = field(default_factory=lambda: ["OPENAI_API_KEY", "APP_TOKEN"])

    def validate(self) -> list[str]:
        """Validate deployment configuration and return any issues."""
        issues = []

        # Check required environment variables
        for env_var in self.required_env_vars:
            if not os.getenv(env_var):
                issues.append(f"Required environment variable not set: {env_var}")

        # Check SSL configuration
        if self.ssl_keyfile and not Path(self.ssl_keyfile).exists():
            issues.append(f"SSL key file not found: {self.ssl_keyfile}")

        if self.ssl_certfile and not Path(self.ssl_certfile).exists():
            issues.append(f"SSL certificate file not found: {self.ssl_certfile}")

        # Check port availability
        if self.port < 1024 and os.getuid() != 0:
            issues.append(f"Port {self.port} requires root privileges")

        return issues


@dataclass
class ProductionConfig:
    """Complete production configuration."""

    security: SecurityConfig = field(default_factory=SecurityConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    deployment: DeploymentConfig = field(default_factory=DeploymentConfig)

    @classmethod
    def from_environment(cls) -> "ProductionConfig":
        """Create configuration from environment variables."""

        config = cls()

        # Security settings
        config.security.require_auth_token = os.getenv("REQUIRE_AUTH_TOKEN", "true").lower() == "true"
        config.security.auth_token_env = os.getenv("AUTH_TOKEN_ENV", "APP_TOKEN")

        cors_origins = os.getenv("CORS_ORIGINS", "")
        if cors_origins:
            config.security.cors_origins = [origin.strip() for origin in cors_origins.split(",")]

        config.security.enable_rate_limiting = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
        config.security.rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

        # Performance settings
        config.performance.workers = int(os.getenv("WORKERS", "4"))
        config.performance.max_connections = int(os.getenv("MAX_CONNECTIONS", "1000"))
        config.performance.log_level = os.getenv("LOG_LEVEL", "INFO")
        config.performance.openai_timeout_seconds = int(os.getenv("OPENAI_TIMEOUT", "60"))

        # Deployment settings
        config.deployment.host = os.getenv("HOST", "0.0.0.0")
        config.deployment.port = int(os.getenv("PORT", "8000"))
        config.deployment.ssl_keyfile = os.getenv("SSL_KEYFILE")
        config.deployment.ssl_certfile = os.getenv("SSL_CERTFILE")

        return config

    def validate(self) -> dict[str, list[str]]:
        """Validate all configuration sections."""

        return {
            "security": self.security.validate(),
            "performance": self.performance.validate(),
            "deployment": self.deployment.validate(),
        }

    def to_fastapi_kwargs(self) -> dict[str, Any]:
        """Convert configuration to FastAPI run_fastapi kwargs."""

        return {
            "host": self.deployment.host,
            "port": self.deployment.port,
            "enable_monitoring": self.performance.enable_monitoring,
            "enable_rate_limiting": self.security.enable_rate_limiting,
            "rate_limit_per_minute": self.security.rate_limit_per_minute,
            "cors_origins": self.security.cors_origins,
            "app_token_env": self.security.auth_token_env if self.security.require_auth_token else "",
        }

    def get_uvicorn_config(self) -> dict[str, Any]:
        """Get Uvicorn server configuration."""

        config = {
            "host": self.deployment.host,
            "port": self.deployment.port,
            "workers": self.performance.workers,
            "log_level": self.performance.log_level.lower(),
            "access_log": True,
            "keepalive_timeout": self.performance.keepalive_timeout,
            "timeout_keep_alive": self.performance.keepalive_timeout,
        }

        # Add SSL configuration if provided
        if self.deployment.ssl_keyfile and self.deployment.ssl_certfile:
            config.update(
                {
                    "ssl_keyfile": self.deployment.ssl_keyfile,
                    "ssl_certfile": self.deployment.ssl_certfile,
                }
            )

        return config


def create_production_config() -> ProductionConfig:
    """Create production configuration from environment."""

    config = ProductionConfig.from_environment()

    # Validate configuration
    validation_results = config.validate()

    # Log validation results
    logger = logging.getLogger(__name__)

    for section, issues in validation_results.items():
        if issues:
            logger.warning(f"Configuration issues in {section}:")
            for issue in issues:
                logger.warning(f"  - {issue}")
        else:
            logger.info(f"Configuration section '{section}' validated successfully")

    return config


def get_environment_info() -> dict[str, Any]:
    """Get information about the current environment."""

    return {
        "python_version": sys.version,
        "platform": sys.platform,
        "environment_variables": {
            key: "***" if "token" in key.lower() or "key" in key.lower() or "secret" in key.lower() else value
            for key, value in os.environ.items()
            if key.startswith(("OPENAI_", "APP_", "CORS_", "LOG_", "HOST", "PORT", "WORKERS"))
        },
        "working_directory": os.getcwd(),
        "user": os.getenv("USER", "unknown"),
    }
