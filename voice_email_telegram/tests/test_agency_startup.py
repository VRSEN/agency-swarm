"""Test agency startup and configuration."""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_agency_imports():
    """Test that agency module can be imported."""
    from agency import agency
    assert agency is not None


def test_agency_has_agents():
    """Test that agency has configured agents."""
    from agency import agency
    # Agency should have agents configured
    assert hasattr(agency, 'shared_instructions')


def test_get_completion_function_exists():
    """Test that get_completion function exists."""
    from agency import get_completion
    assert callable(get_completion)
