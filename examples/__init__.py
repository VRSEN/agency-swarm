# Make the examples directory into a package to avoid top-level module name collisions.
# This is needed so that mypy treats files like examples/customer_service/main.py and
# examples/researcher_app/main.py as distinct modules rather than both named "main".

"""
Agency Swarm Examples

This package contains comprehensive examples demonstrating various Agency Swarm capabilities:

- Multi-agent communication and coordination patterns
- File processing, vision analysis, and content handling
- Real-time streaming responses and event processing
- Custom persistence and data management implementations
- Response validation and error handling patterns
- Agency context sharing between agents
- Complex workflow orchestration across multiple agents

Each example is self-contained and can be run independently with proper environment setup.
See individual files for specific implementation details and usage instructions.
"""
