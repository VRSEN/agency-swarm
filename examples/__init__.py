# Make the examples directory into a package to avoid top-level module name collisions.
# This is needed so that mypy treats files like examples/customer_service/main.py and
# examples/researcher_app/main.py as distinct modules rather than both named "main".

"""
Agency Swarm Examples

This package contains comprehensive examples demonstrating various Agency Swarm capabilities:

- file_handling.py: File processing and vision analysis
- two_agent_conversation.py: Multi-agent communication patterns
- multi_agent_workflow.py: Complex multi-agent workflows
- streaming_demo.py: Real-time streaming responses and event processing
- file_search.py: File search and content analysis
- custom_persistence.py: Custom persistence implementation
- hosted_tool_preservation.py: Tool preservation patterns

Each example is self-contained and can be run independently with proper environment setup.
"""
