import dataclasses
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("ag_ui")
from ag_ui.core import (
    AssistantMessage,
    CustomEvent,
    DeveloperMessage,
    EventType,
    FunctionCall,
    MessagesSnapshotEvent,
    RawEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCall,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolMessage,
    UserMessage,
)
from openai.types.responses import (
    ResponseCodeInterpreterToolCall,
    ResponseFileSearchToolCall,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from openai.types.responses.response_file_search_tool_call import Result as FileSearchResult
from openai.types.responses.response_function_call_arguments_delta_event import ResponseFunctionCallArgumentsDeltaEvent
from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent
from openai.types.responses.response_output_item_done_event import ResponseOutputItemDoneEvent
from openai.types.responses.response_output_text import AnnotationFileCitation
from openai.types.responses.response_text_delta_event import Logprob, ResponseTextDeltaEvent
from pydantic import BaseModel

from agency_swarm.ui.core.agui_adapter import AguiAdapter
from agency_swarm.utils.serialization import serialize


def make_raw_event(data):
    return SimpleNamespace(type="raw_response_event", data=data)


def make_stream_event(name, item):
    return SimpleNamespace(type="run_item_stream_event", name=name, item=item)


class DummyModel:
    def __init__(self, value: str):
        self.value = value


def test_serialize_handles_basic_values_and_objects():
    @dataclasses.dataclass
    class Payload:
        name: str
        count: int

    payload = Payload(name="test", count=3)
    obj = DummyModel(value="42")

    serialized = serialize({"payload": payload, "wrapped": obj, "items": [1, True]})

    assert serialized["payload"] == {"name": "test", "count": "3"}
    assert serialized["wrapped"] == {"value": "42"}
    assert serialized["items"] == ["1", "True"]


def test_serialize_handles_nested_models_and_mocks():
    class Model(BaseModel):
        number: int

    nested = Model(number=7)
    agent = MagicMock()
    agent.name = "Coach"
    agent.model = "gpt-4"

    serialized = serialize({"nested": nested, "agent": agent})

    assert serialized["nested"] == {"number": "7"}
    assert serialized["agent"]["name"] == "Coach"
    assert serialized["agent"]["model"] == "gpt-4"
    assert "method_calls" in serialized["agent"]


def test_agui_messages_to_chat_history_converts_roles_and_tool_calls():
    tool_call = ToolCall(id="call-1", type="function", function=FunctionCall(name="Weather", arguments="{}"))
    assistant_msg = AssistantMessage(id="a1", role="assistant", content="Hi", tool_calls=[tool_call])
    user_msg = UserMessage(id="u1", role="user", content="Hello")
    tool_msg = ToolMessage(id="t1", role="tool", content="Done", tool_call_id="call-1")
    dev_msg = DeveloperMessage(id="d1", role="developer", content="Dev note")

    history = AguiAdapter().agui_messages_to_chat_history([user_msg, assistant_msg, tool_msg, dev_msg])

    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1]["type"] == "function_call"
    assert history[1]["name"] == "Weather"
    assert history[2] == {"call_id": "call-1", "output": "Done", "type": "function_call_output"}
    assert history[3] == {"role": "system", "content": "Dev note"}


def test_agui_messages_to_chat_history_handles_file_search_call():
    tool_call = ToolCall(
        id="call-99",
        type="function",
        function=FunctionCall(name="FileSearchTool", arguments='{"queries": ["foo"], "results": ["bar"]}'),
    )
    assistant_msg = AssistantMessage(id="a2", role="assistant", content="", tool_calls=[tool_call])

    history = AguiAdapter().agui_messages_to_chat_history([assistant_msg])

    assert history[0]["type"] == "file_search_call"
    assert history[0]["queries"] == ["foo"]
    assert history[0]["results"] == ["bar"]


def test_agui_messages_to_chat_history_handles_code_interpreter_call():
    tool_call = ToolCall(
        id="ci-1",
        type="function",
        function=FunctionCall(
            name="CodeInterpreterTool",
            arguments='{"code": "print(1)", "container_id": "cid", "outputs": ["1"]}',
        ),
    )
    assistant_msg = AssistantMessage(id="a3", role="assistant", content="", tool_calls=[tool_call])

    history = AguiAdapter().agui_messages_to_chat_history([assistant_msg])

    assert history[0]["type"] == "code_interpreter_call"
    assert history[0]["code"] == "print(1)"
    assert history[0]["outputs"] == ["1"]


def test_agui_messages_to_chat_history_handles_plain_assistant_message():
    assistant_msg = AssistantMessage(id="a4", role="assistant", content="Result ready", tool_calls=[])

    history = AguiAdapter().agui_messages_to_chat_history([assistant_msg])

    assert history == [{"role": "assistant", "content": "Result ready"}]


def test_openai_events_emit_message_lifecycle():
    adapter = AguiAdapter()
    run_id = "run-1"

    message = ResponseOutputMessage(
        id="m-1",
        content=[ResponseOutputText(annotations=[], text="Hi", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )

    start_event = make_raw_event(
        ResponseOutputItemAddedEvent(
            item=message,
            output_index=0,
            sequence_number=1,
            type="response.output_item.added",
        )
    )

    delta_event = make_raw_event(
        ResponseTextDeltaEvent(
            content_index=0,
            delta="Hi",
            item_id="m-1",
            logprobs=[],
            output_index=0,
            sequence_number=2,
            type="response.output_text.delta",
        )
    )
    done_event = make_raw_event(
        ResponseOutputItemDoneEvent(
            item=message,
            output_index=0,
            sequence_number=3,
            type="response.output_item.done",
        )
    )

    start = adapter.openai_to_agui_events(start_event, run_id=run_id)
    delta = adapter.openai_to_agui_events(delta_event, run_id=run_id)
    done = adapter.openai_to_agui_events(done_event, run_id=run_id)

    assert isinstance(start, TextMessageStartEvent)
    assert isinstance(delta, TextMessageContentEvent)
    assert isinstance(done, TextMessageEndEvent)
    assert delta.message_id == "m-1"


def test_openai_events_track_tool_calls_and_arguments():
    adapter = AguiAdapter()
    run_id = "run-2"
    raw_tool = ResponseFunctionToolCall(
        arguments="{}",
        call_id="call-1",
        name="search",
        type="function_call",
        id="item-1",
        status="in_progress",
    )

    adapter.openai_to_agui_events(
        make_raw_event(
            ResponseOutputItemAddedEvent(
                item=raw_tool,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            )
        ),
        run_id=run_id,
    )
    args_event = adapter.openai_to_agui_events(
        make_raw_event(
            ResponseFunctionCallArgumentsDeltaEvent(
                item_id="item-1",
                delta='{"q": "',
                output_index=0,
                sequence_number=2,
                type="response.function_call_arguments.delta",
            )
        ),
        run_id=run_id,
    )
    done_events = adapter.openai_to_agui_events(
        make_raw_event(
            ResponseOutputItemDoneEvent(
                type="response.output_item.done",
                item=ResponseFunctionToolCall(
                    arguments='{"q": "weather"}',
                    call_id="call-1",
                    name="search",
                    type="function_call",
                    id="item-1",
                    status="completed",
                ),
                output_index=0,
                sequence_number=3,
            )
        ),
        run_id=run_id,
    )

    assert isinstance(args_event, ToolCallArgsEvent)
    assert args_event.tool_call_id == "call-1"
    assert isinstance(done_events, list)
    assert isinstance(done_events[0], ToolCallEndEvent)
    assert isinstance(done_events[1], MessagesSnapshotEvent)


def test_openai_typed_events_emit_message_lifecycle():
    adapter = AguiAdapter()
    run_id = "typed-run"

    message = ResponseOutputMessage(
        id="msg-typed",
        content=[ResponseOutputText(annotations=[], text="Hello world", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )

    start_event = ResponseOutputItemAddedEvent(
        item=message,
        output_index=0,
        sequence_number=1,
        type="response.output_item.added",
    )
    delta_event = ResponseTextDeltaEvent(
        content_index=0,
        delta="!",
        item_id="msg-typed",
        logprobs=[Logprob(token="!", logprob=0.0, top_logprobs=[])],
        output_index=0,
        sequence_number=2,
        type="response.output_text.delta",
    )
    done_event = ResponseOutputItemDoneEvent(
        item=message,
        output_index=0,
        sequence_number=3,
        type="response.output_item.done",
    )

    start = adapter.openai_to_agui_events(make_raw_event(start_event), run_id=run_id)
    delta = adapter.openai_to_agui_events(make_raw_event(delta_event), run_id=run_id)
    done = adapter.openai_to_agui_events(make_raw_event(done_event), run_id=run_id)

    assert isinstance(start, TextMessageStartEvent)
    assert isinstance(delta, TextMessageContentEvent)
    assert isinstance(done, TextMessageEndEvent)
    assert delta.message_id == "msg-typed"


def test_openai_events_handles_exceptions_with_run_error():
    adapter = AguiAdapter()
    event = MagicMock()
    event.type = "raw_response_event"

    type(event).data = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

    result = adapter.openai_to_agui_events(event, run_id="oops")

    assert result.type == EventType.RUN_ERROR
    assert "boom" in result.message


def test_openai_events_ignore_message_without_id():
    adapter = AguiAdapter()
    event = make_raw_event(
        SimpleNamespace(
            type="response.output_item.added",
            item=SimpleNamespace(type="message", role="assistant", id=None),
        )
    )

    result = adapter.openai_to_agui_events(event, run_id="missing-message")

    assert isinstance(result, RawEvent)
    assert result.type == EventType.RAW
    assert result.event["data"]["type"] == "response.output_item.added"


def test_openai_events_ignore_tool_call_without_call_id():
    adapter = AguiAdapter()
    run_id = "missing-tool"
    tool = SimpleNamespace(type="function_call", id="item-99", call_id=None, name="search", arguments="{}")

    adapter.openai_to_agui_events(
        make_raw_event(SimpleNamespace(type="response.output_item.added", item=tool)),
        run_id=run_id,
    )
    args_event = adapter.openai_to_agui_events(
        make_raw_event(SimpleNamespace(type="response.function_call_arguments.delta", item_id="item-99", delta="{}")),
        run_id=run_id,
    )

    assert isinstance(args_event, RawEvent)
    assert args_event.type == EventType.RAW
    assert args_event.event["data"]["type"] == "response.function_call_arguments.delta"


def test_openai_events_ignore_text_delta_without_item_id():
    adapter = AguiAdapter()
    event = make_raw_event(SimpleNamespace(type="response.output_text.delta", item_id=None, delta="Hi"))

    result = adapter.openai_to_agui_events(event, run_id="missing-delta-id")

    assert isinstance(result, RawEvent)
    assert result.type == EventType.RAW
    assert result.event["data"]["type"] == "response.output_text.delta"


def test_openai_events_ignore_tool_done_without_call_id():
    adapter = AguiAdapter()
    raw_item = SimpleNamespace(type="function_call", id="item-9", call_id=None, name="search", arguments="{}")
    event = make_raw_event(SimpleNamespace(type="response.output_item.done", item=raw_item))

    result = adapter.openai_to_agui_events(event, run_id="tool-done-missing")

    assert isinstance(result, RawEvent)
    assert result.type == EventType.RAW
    assert result.event["data"]["type"] == "response.output_item.done"


def test_run_item_stream_events_emit_snapshots():
    adapter = AguiAdapter()
    run_id = "run-3"
    output_content = ResponseOutputText(annotations=[], text="Answer", type="output_text")
    raw_item = ResponseOutputMessage(
        id="msg-1",
        content=[output_content],
        role="assistant",
        status="completed",
        type="message",
    )
    item = SimpleNamespace(raw_item=raw_item)

    events = adapter.openai_to_agui_events(make_stream_event("message_output_created", item), run_id=run_id)

    assert isinstance(events, list)
    assert all(isinstance(e, MessagesSnapshotEvent | CustomEvent) for e in events)
    assert any(isinstance(e, MessagesSnapshotEvent) for e in events)


def test_run_item_stream_with_annotations_returns_custom_event():
    adapter = AguiAdapter()
    run_id = "annotated"
    annotation = AnnotationFileCitation(file_id="file-annot", filename="doc.pdf", index=1, type="file_citation")
    output_content = ResponseOutputText(annotations=[annotation], text="Answer", type="output_text")
    raw_item = ResponseOutputMessage(
        id="msg-annot",
        content=[output_content],
        role="assistant",
        status="completed",
        type="message",
    )
    item = SimpleNamespace(raw_item=raw_item)

    events = adapter.openai_to_agui_events(make_stream_event("message_output_created", item), run_id=run_id)

    assert isinstance(events, list)
    assert any(isinstance(e, CustomEvent) for e in events)
    custom = next(e for e in events if isinstance(e, CustomEvent))
    assert custom.value["annotations"] == [annotation.model_dump()]


def test_run_item_stream_ignores_message_without_text():
    adapter = AguiAdapter()
    run_id = "missing-text"
    output_content = SimpleNamespace(text=None, annotations=None)
    raw_item = SimpleNamespace(id="msg-empty", content=[output_content])
    item = SimpleNamespace(raw_item=raw_item)

    result = adapter.openai_to_agui_events(make_stream_event("message_output_created", item), run_id=run_id)

    assert isinstance(result, RawEvent)
    assert result.type == EventType.RAW
    assert result.event["name"] == "message_output_created"


def test_tool_output_stream_event_converts_to_tool_message():
    adapter = AguiAdapter()
    run_id = "run-4"
    item = SimpleNamespace(raw_item={"call_id": "call-7"}, call_id="call-7", output="done")

    event = adapter.openai_to_agui_events(make_stream_event("tool_output", item), run_id=run_id)

    assert isinstance(event, MessagesSnapshotEvent)
    message = event.messages[0]
    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-7"
    assert message.content == "done"


def test_tool_output_without_call_id_is_ignored():
    adapter = AguiAdapter()
    item = SimpleNamespace(raw_item={}, call_id=None, output="done")

    result = adapter.openai_to_agui_events(make_stream_event("tool_output", item), run_id="tool-missing")

    assert isinstance(result, RawEvent)
    assert result.type == EventType.RAW
    assert result.event["name"] == "tool_output"


def test_run_item_stream_unknown_event_is_returned_as_raw_event():
    adapter = AguiAdapter()
    run_id = "unknown-stream"
    unknown_event = make_stream_event("unhandled_event", None)

    result = adapter.openai_to_agui_events(unknown_event, run_id=run_id)

    assert isinstance(result, RawEvent)
    assert result.type == EventType.RAW
    assert result.event["name"] == "unhandled_event"
    assert result.event["type"] == "run_item_stream_event"


def test_tool_meta_handles_non_function_tools():
    adapter = AguiAdapter()

    typed_file_search = ResponseFileSearchToolCall(
        id="file-1",
        queries=["foo"],
        status="completed",
        type="file_search_call",
        results=[FileSearchResult(file_id="doc", text="bar")],
    )
    typed_code_interpreter = ResponseCodeInterpreterToolCall(
        code="print(42)",
        container_id="cont",
        id="ci-7",
        outputs=[{"type": "logs", "logs": "42"}],
        type="code_interpreter_call",
        status="completed",
    )

    @dataclasses.dataclass
    class LegacyFileSearchCall:
        type: str
        id: str
        queries: list[str]
        results: list[dict]

    @dataclasses.dataclass
    class LegacyCodeInterpreterCall:
        type: str
        id: str
        code: str
        container_id: str
        outputs: list[dict]

    file_search = LegacyFileSearchCall(
        type="file_search_call",
        id=typed_file_search.id,
        queries=typed_file_search.queries or [],
        results=json.loads(typed_file_search.model_dump_json())["results"],
    )
    code_interpreter = LegacyCodeInterpreterCall(
        type="code_interpreter_call",
        id=typed_code_interpreter.id,
        code=typed_code_interpreter.code or "",
        container_id=typed_code_interpreter.container_id,
        outputs=[{"type": "logs", "logs": "42"}],
    )

    file_meta = adapter._tool_meta(file_search)
    code_meta = adapter._tool_meta(code_interpreter)

    assert file_meta[0] == "file-1"
    assert file_meta[1] == "FileSearchTool"
    assert json.loads(file_meta[2])["queries"] == ["foo"]

    assert code_meta[0] == "ci-7"
    assert code_meta[1] == "CodeInterpreterTool"
    assert json.loads(code_meta[2])["code"] == "print(42)"
