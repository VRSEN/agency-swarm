import pytest

from agency_swarm.ui.demos.launcher import TerminalDemoLauncher


class DummyConsole:
    def print(self, *args, **kwargs):
        pass

    def rule(self):
        pass


class DummyEventConverter:
    def __init__(self):
        self.console = DummyConsole()


class DummyThreadManager:
    def __init__(self):
        self.cleared = False
        self.added_message = None

    def get_all_messages(self):
        return [{"role": "user", "content": "hi"}]

    def clear(self):
        self.cleared = True

    def add_message(self, msg):
        self.added_message = msg


class DummyAgency:
    def __init__(self):
        self.thread_manager = DummyThreadManager()
        self.last_run_config = None

    async def get_response(self, message, run_config):
        self.last_run_config = run_config

        class Result:
            final_output = "summary"

        return Result()


@pytest.mark.asyncio
async def test_compact_uses_nano_without_temperature():
    agency = DummyAgency()
    event_converter = DummyEventConverter()

    new_chat_id = await TerminalDemoLauncher._compact_conversation(agency, event_converter, [])

    assert agency.last_run_config.model == "gpt-5-nano"
    assert getattr(agency.last_run_config, "model_settings", None) is None
    assert new_chat_id.startswith("run_demo_chat_")


@pytest.mark.asyncio
async def test_compact_resets_thread_and_adds_summary():
    agency = DummyAgency()
    event_converter = DummyEventConverter()

    await TerminalDemoLauncher._compact_conversation(agency, event_converter, [])

    assert agency.thread_manager.cleared is True
    assert agency.thread_manager.added_message == {"role": "system", "content": "summary"}
