import time
from unittest.mock import Mock

import pytest

from agency_swarm.agents import Agent
from agency_swarm.threads.thread import Thread
from agency_swarm.user import User


@pytest.fixture
def thread_and_agent():
    mock_client = Mock()
    mock_user = User()
    test_agent = Agent(name="TestAgent", description="", instructions="")
    thread = Thread(mock_user, test_agent)
    thread.client = mock_client
    thread.id = "test_thread_id"
    thread._thread = Mock()
    thread._run = Mock()
    thread._run.id = "test_run_id"
    thread._create_run = Mock()
    return thread, test_agent


def test_retry_on_rate_limit(thread_and_agent, monkeypatch):
    thread, agent = thread_and_agent
    thread._run.last_error = Mock()
    thread._run.last_error.message = "Rate limit is exceeded. Try again in 2 seconds."

    called = []

    def fake_sleep(sec):
        called.append(sec)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    result = thread._try_run_failed_recovery(
        error_attempts=0,
        recipient_agent=agent,
        additional_instructions=None,
        event_handler=None,
        tool_choice=None,
        response_format=None,
        parent_run_id=None,
    )

    assert result is True
    thread._create_run.assert_called_once()
    assert called and called[0] == 2
