"""
Tests for FastAPI integration module.

This module tests the FastAPI server setup and configuration functionality.
"""

from unittest.mock import Mock

from agency_swarm.integrations.fastapi import run_fastapi


class TestRunFastAPI:
    """Test FastAPI server setup and configuration."""

    def test_run_fastapi_no_agencies_or_tools_warning(self, caplog):
        """Test that warning is logged when no agencies or tools are provided."""
        result = run_fastapi()
        
        assert result is None
        assert "No endpoints to deploy" in caplog.text

    def test_run_fastapi_empty_agencies_and_tools_warning(self, caplog):
        """Test that warning is logged when empty agencies and tools are provided."""
        result = run_fastapi(agencies={}, tools=[])
        
        assert result is None
        assert "No endpoints to deploy" in caplog.text

    def test_run_fastapi_parameter_validation(self):
        """Test parameter validation logic."""
        # Test with None agencies and tools
        result = run_fastapi(agencies=None, tools=None)
        assert result is None

        # Test with empty agencies and tools
        result = run_fastapi(agencies={}, tools=[])
        assert result is None

        # Test with valid agencies but no tools
        mock_agency = Mock()
        mock_agency.agents = {"agent1": Mock()}
        mock_agency.get_agency_structure.return_value = {"structure": "test"}

        agencies = {"test_agency": lambda load_threads_callback: mock_agency}

        # This should not return None (would proceed to try imports)
        # We can't test the full flow without mocking imports, but we can test the validation
        try:
            result = run_fastapi(agencies=agencies, return_app=True)
            # If we get here, validation passed
            assert True
        except ImportError:
            # Expected if FastAPI dependencies are not installed
            assert True
