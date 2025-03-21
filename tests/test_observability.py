import os
import unittest
from unittest.mock import patch
import sqlite3

from dotenv import load_dotenv

from agency_swarm.util.tracking import init_tracking, stop_tracking


class ObservabilityTest(unittest.TestCase):
    """Test suite for observability features including local, langfuse, and agentops trackers."""

    @classmethod
    def setUpClass(cls):
        """Set up the test environment by loading environment variables."""
        load_dotenv()

    def setUp(self):
        """Reset tracking state before each test."""
        stop_tracking()
        
        # Remove the local SQLite database if it exists
        if os.path.exists("events.db"):
            os.remove("events.db")

    def tearDown(self):
        """Clean up after each test."""
        stop_tracking()

    def test_local_tracking(self):
        """Test that local tracking initializes and creates a SQLite database."""
        # Initialize local tracking
        init_tracking("local")
        
        # Check if SQLite database was created
        self.assertTrue(os.path.exists("events.db"), "Local tracking SQLite database was not created")
        
        # Verify the database has the expected schema
        conn = sqlite3.connect("events.db")
        cursor = conn.cursor()
        
        # Check if events table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
        tables = cursor.fetchall()
        self.assertTrue(len(tables) > 0, "Events table was not created in SQLite database")
        
        # Check column structure
        cursor.execute("PRAGMA table_info(events)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        required_columns = ["event_id", "run_id", "event_time", "callback_type"]
        for col in required_columns:
            self.assertIn(col, column_names, f"Required column '{col}' not found in events table")
        
        conn.close()

    @patch("langfuse.client.Langfuse")
    def test_langfuse_tracking(self, mock_langfuse):
        """Test that langfuse tracking initializes correctly with environment variables."""
        # Set up mock for langfuse client
        mock_langfuse_instance = mock_langfuse.return_value
        
        # Check if required environment variables are set
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        
        if not secret_key or not public_key:
            self.skipTest("LANGFUSE_SECRET_KEY or LANGFUSE_PUBLIC_KEY not set in environment")
        
        # Initialize langfuse tracking
        init_tracking("langfuse")
        
        # Verify that langfuse client was created
        mock_langfuse.assert_called_once()

    @patch("agentops.init")
    def test_agentops_tracking(self, mock_agentops_init):
        """Test that agentops tracking initializes correctly with environment variables."""
        # Check if required environment variable is set
        api_key = os.environ.get("AGENTOPS_API_KEY")
        
        if not api_key:
            self.skipTest("AGENTOPS_API_KEY not set in environment")
        
        # Initialize agentops tracking
        init_tracking("agentops")
        
        # Verify that agentops was initialized
        mock_agentops_init.assert_called_once()

    def test_observability_dependencies(self):
        """Test that all required dependencies for observability features are installed."""
        # If these imports fail, the test will fail with ImportError
        missing_deps = []
        
        try:
            import tiktoken
        except ImportError:
            missing_deps.append("tiktoken")
            
        try:
            import langchain
        except ImportError:
            missing_deps.append("langchain")
            
        try:
            import langchain_community
        except ImportError:
            missing_deps.append("langchain_community")
            
        try:
            from langfuse.callback import CallbackHandler
        except ImportError:
            missing_deps.append("langfuse")
            
        try:
            from agentops.partners.langchain_callback_handler import LangchainCallbackHandler
        except ImportError:
            missing_deps.append("agentops")
        
        # Print helpful error message if dependencies are missing
        if missing_deps:
            self.fail(f"Missing required dependencies for observability: {', '.join(missing_deps)}.\n"
                      f"Please install with: pip install {' '.join(missing_deps)}")


if __name__ == "__main__":
    unittest.main()