# --- Agency package init ---
"""
Agency package for orchestrating multi-agent systems.

Split into modules for maintainability:
- core: Main Agency class and initialization
- setup: Agent registration and configuration
- responses: Modern response methods
- helpers: Utility helper functions
- visualization: Structure visualization and demos
"""

# Export the main Agency class and type aliases
from .core import Agency, CommunicationFlowEntry

# All public API should go through the core Agency class
__all__ = [
    "Agency",
    "CommunicationFlowEntry",
]
