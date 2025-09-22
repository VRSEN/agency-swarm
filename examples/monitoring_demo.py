#!/usr/bin/env python3
"""
Production Monitoring Demo for Agency Swarm

This example demonstrates the comprehensive monitoring capabilities
including health checks, metrics collection, and production-ready endpoints.

Features demonstrated:
- Health check endpoints (/health, /ready, /metrics)
- Performance metrics collection
- Security headers and rate limiting
- System resource monitoring
- OpenAI API connectivity checks

Usage:
    python examples/monitoring_demo.py

Then visit:
- http://localhost:8000/health - Basic health check
- http://localhost:8000/ready - Detailed readiness check
- http://localhost:8000/metrics - Performance metrics
- http://localhost:8000/docs - API documentation
"""

import os

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi import run_fastapi


def create_demo_agency(load_threads_callback=None, save_threads_callback=None):
    """Create a demo agency for monitoring demonstration."""

    # Create a simple agent
    demo_agent = Agent(
        name="MonitoringDemoAgent",
        instructions="""
        You are a demo agent for showcasing monitoring capabilities.

        Your role is to:
        1. Respond to user queries about monitoring
        2. Provide information about system health
        3. Demonstrate API functionality for monitoring tests

        Keep responses brief and informative.
        """,
        model="gpt-4o-mini",
    )

    # Create agency
    agency = Agency(
        demo_agent,
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
    )

    return agency


def main():
    """Run the monitoring demo server."""

    print("🚀 Starting Agency Swarm with Production Monitoring")
    print("=" * 60)

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  WARNING: OPENAI_API_KEY not set")
        print("   Health checks will show degraded status")
        print("   Set OPENAI_API_KEY environment variable for full functionality")
        print()

    # Configuration
    config = {
        "agencies": {"demo": create_demo_agency},
        "host": "0.0.0.0",
        "port": 8000,
        "enable_monitoring": True,
        "enable_rate_limiting": True,
        "rate_limit_per_minute": 60,
        "cors_origins": ["*"],
        "app_token_env": "",  # Disable auth for demo
    }

    print("📊 Monitoring Features Enabled:")
    print("   ✅ Health check endpoints (/health, /ready)")
    print("   ✅ Performance metrics (/metrics)")
    print("   ✅ Security headers")
    print("   ✅ Rate limiting (60 req/min)")
    print("   ✅ System resource monitoring")
    print("   ✅ OpenAI API connectivity checks")
    print()

    print("🔗 Available Endpoints:")
    print("   • http://localhost:8000/health - Basic health check")
    print("   • http://localhost:8000/ready - Detailed readiness check")
    print("   • http://localhost:8000/metrics - Performance metrics")
    print("   • http://localhost:8000/docs - API documentation")
    print("   • http://localhost:8000/demo/response - Demo agent endpoint")
    print()

    print("🧪 Test Commands:")
    print("   # Basic health check")
    print("   curl http://localhost:8000/health")
    print()
    print("   # Detailed readiness check")
    print("   curl http://localhost:8000/ready")
    print()
    print("   # Performance metrics")
    print("   curl http://localhost:8000/metrics")
    print()
    print("   # Test rate limiting (run multiple times quickly)")
    print("   for i in {1..70}; do curl -s http://localhost:8000/health; done")
    print()

    print("🏥 Health Check Status Meanings:")
    print("   • healthy: All systems operational")
    print("   • degraded: Some issues but service functional")
    print("   • unhealthy: Critical issues, service may not work")
    print()

    print("📈 Metrics Collected:")
    print("   • Request count and error rates")
    print("   • Response time percentiles (p50, p95, p99)")
    print("   • System resource usage (CPU, memory, disk)")
    print("   • Service uptime")
    print()

    try:
        # Start the server
        print("🌟 Starting server...")
        print("   Press Ctrl+C to stop")
        print("=" * 60)

        run_fastapi(**config)

    except KeyboardInterrupt:
        print("\n👋 Shutting down monitoring demo")
        print("   Thanks for testing Agency Swarm monitoring!")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        print("   Check the configuration and try again")


if __name__ == "__main__":
    main()
