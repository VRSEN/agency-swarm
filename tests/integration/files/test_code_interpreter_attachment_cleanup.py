"""Attachment cleanup through the real Agency and SDK runner, using an offline model."""

import pytest
from agents import CodeInterpreterTool

from agency_swarm import Agency, Agent
from tests.deterministic_model import DeterministicModel


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("existing_file_ids", [None, [], ["file-existing"]])
async def test_run_restores_code_interpreter_attachments(
    monkeypatch: pytest.MonkeyPatch, streaming: bool, existing_file_ids: list[str] | None
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_AGENTS_DISABLE_TRACING", "1")
    agent = Agent(name="AttachmentReader", model=DeterministicModel())
    original_tool = None
    if existing_file_ids is not None:
        original_tool = CodeInterpreterTool(
            tool_config={
                "type": "code_interpreter",
                "container": {"type": "auto", "file_ids": list(existing_file_ids)},
            }
        )
        agent.add_tool(original_tool)
    assert agent.attachment_manager is not None

    def filename(file_id: str) -> str:
        return f"{file_id}.csv"

    monkeypatch.setattr(agent.attachment_manager, "_get_filename_by_id", filename)
    agency = Agency(agent)
    file_ids = [*(existing_file_ids or []), "file-one", "file-two"]

    if streaming:
        response = agency.get_response_stream("Ready", file_ids=file_ids)
        async for _ in response:
            pass
        assert response.final_output == "OK"
    else:
        result = await agency.get_response("Ready", file_ids=file_ids)
        assert result.final_output == "OK"

    tools = [tool for tool in agent.tools if isinstance(tool, CodeInterpreterTool)]
    if original_tool is None:
        assert tools == []
    else:
        assert tools == [original_tool]
        assert original_tool.tool_config["container"] == {"type": "auto", "file_ids": existing_file_ids}
