"""Test agent configurations."""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_ceo_agent_exists():
    """Test that CEO agent is configured."""
    from ceo.ceo import ceo
    assert ceo is not None
    assert ceo.name == "CEO"
    assert ceo.model == "gpt-5"


def test_email_specialist_exists():
    """Test that EmailSpecialist agent is configured."""
    from email_specialist.email_specialist import email_specialist
    assert email_specialist is not None
    assert email_specialist.name == "EmailSpecialist"
    assert email_specialist.model == "gpt-5"


def test_memory_manager_exists():
    """Test that MemoryManager agent is configured."""
    from memory_manager.memory_manager import memory_manager
    assert memory_manager is not None
    assert memory_manager.name == "MemoryManager"
    assert memory_manager.model == "gpt-5"


def test_voice_handler_exists():
    """Test that VoiceHandler agent is configured."""
    from voice_handler.voice_handler import voice_handler
    assert voice_handler is not None
    assert voice_handler.name == "VoiceHandler"
    assert voice_handler.model == "gpt-5"
