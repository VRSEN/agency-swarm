from unittest.mock import patch

import pytest
from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.usage_tracking import LangfuseUsageTracker, SQLiteUsageTracker


@pytest.fixture
def sqlite_tracker():
    return SQLiteUsageTracker(":memory:")


@pytest.fixture
def langfuse_tracker():
    return LangfuseUsageTracker(api_key="test_key", project_id="test_project")


def test_sqlite_track_and_get_total_tokens(sqlite_tracker):
    usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    sqlite_tracker.track_usage(usage)
    totals = sqlite_tracker.get_total_tokens()
    assert totals.model_dump() == usage.model_dump()


@patch("requests.post")
def test_langfuse_track_usage(mock_post, langfuse_tracker):
    usage = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
    mock_post.return_value.status_code = 200

    langfuse_tracker.track_usage(usage)

    mock_post.assert_called_once_with(
        f"https://api.langfuse.com/projects/test_project/token-usage",
        json=usage.model_dump(),
        headers={
            "Authorization": "Bearer test_key",
            "Content-Type": "application/json",
        },
    )


def test_langfuse_get_total_tokens(langfuse_tracker):
    totals = langfuse_tracker.get_total_tokens()
    assert totals == Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    from agency_swarm import Agency, Agent

    agent = Agent(name="test_agent")
    agency = Agency(agency_chart=[agent])
    agency.demo_gradio()
