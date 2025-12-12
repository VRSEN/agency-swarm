"""Tests for handling LiteLLM/Chat Completions placeholder IDs.

When using non-Responses API models (LiteLLM, Chat Completions), the SDK emits
`item.id = "__fake_id__"` for all output items. This causes collisions when
using item.id as a map key. These tests verify the fix: skip placeholder IDs
and use call_id for correlation instead.
"""

from types import SimpleNamespace

import pytest
from agents.models.fake_id import FAKE_RESPONSES_ID

pytest.importorskip("ag_ui")
from ag_ui.core import ToolCallArgsEvent
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses.response_function_call_arguments_delta_event import (
    ResponseFunctionCallArgumentsDeltaEvent,
)
from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent

from agency_swarm.ui.core.agui_adapter import AguiAdapter


def make_raw_event(data):
    return SimpleNamespace(type="raw_response_event", data=data)


class TestAguiAdapterFakeIdHandling:
    """Tests for agui_adapter handling of __fake_id__ placeholder."""

    def test_multiple_tool_calls_with_fake_id_are_tracked_separately(self):
        """Multiple tool calls sharing __fake_id__ should each be tracked by call_id."""
        adapter = AguiAdapter()
        run_id = "fake-id-run"

        # First tool call with __fake_id__
        tool1 = ResponseFunctionToolCall(
            arguments="{}",
            call_id="call_first_tool",
            name="tool_one",
            type="function_call",
            id=FAKE_RESPONSES_ID,  # Same placeholder ID
            status="in_progress",
        )

        # Second tool call with same __fake_id__
        tool2 = ResponseFunctionToolCall(
            arguments="{}",
            call_id="call_second_tool",
            name="tool_two",
            type="function_call",
            id=FAKE_RESPONSES_ID,  # Same placeholder ID
            status="in_progress",
        )

        # Register first tool
        adapter.openai_to_agui_events(
            make_raw_event(
                ResponseOutputItemAddedEvent(
                    item=tool1,
                    output_index=0,
                    sequence_number=1,
                    type="response.output_item.added",
                )
            ),
            run_id=run_id,
        )

        # Register second tool
        adapter.openai_to_agui_events(
            make_raw_event(
                ResponseOutputItemAddedEvent(
                    item=tool2,
                    output_index=1,
                    sequence_number=2,
                    type="response.output_item.added",
                )
            ),
            run_id=run_id,
        )

        # Send delta for first tool - should map to call_first_tool
        # Using call_id directly since item_id is the placeholder
        delta1_event = adapter.openai_to_agui_events(
            make_raw_event(
                ResponseFunctionCallArgumentsDeltaEvent(
                    item_id=FAKE_RESPONSES_ID,
                    delta='{"arg1": "value1"}',
                    output_index=0,  # First tool's output_index
                    sequence_number=3,
                    type="response.function_call_arguments.delta",
                )
            ),
            run_id=run_id,
        )

        # Send delta for second tool - should map to call_second_tool
        delta2_event = adapter.openai_to_agui_events(
            make_raw_event(
                ResponseFunctionCallArgumentsDeltaEvent(
                    item_id=FAKE_RESPONSES_ID,
                    delta='{"arg2": "value2"}',
                    output_index=1,  # Second tool's output_index
                    sequence_number=4,
                    type="response.function_call_arguments.delta",
                )
            ),
            run_id=run_id,
        )

        # Both deltas should be properly mapped to different call_ids
        assert isinstance(delta1_event, ToolCallArgsEvent)
        assert isinstance(delta2_event, ToolCallArgsEvent)
        assert delta1_event.tool_call_id == "call_first_tool"
        assert delta2_event.tool_call_id == "call_second_tool"

    def test_tool_call_with_real_id_still_works(self):
        """Tool calls with real item IDs should continue to work."""
        adapter = AguiAdapter()
        run_id = "real-id-run"

        tool = ResponseFunctionToolCall(
            arguments="{}",
            call_id="call_real",
            name="real_tool",
            type="function_call",
            id="real_item_id",  # Real ID, not placeholder
            status="in_progress",
        )

        adapter.openai_to_agui_events(
            make_raw_event(
                ResponseOutputItemAddedEvent(
                    item=tool,
                    output_index=0,
                    sequence_number=1,
                    type="response.output_item.added",
                )
            ),
            run_id=run_id,
        )

        delta_event = adapter.openai_to_agui_events(
            make_raw_event(
                ResponseFunctionCallArgumentsDeltaEvent(
                    item_id="real_item_id",
                    delta='{"key": "value"}',
                    output_index=0,
                    sequence_number=2,
                    type="response.function_call_arguments.delta",
                )
            ),
            run_id=run_id,
        )

        assert isinstance(delta_event, ToolCallArgsEvent)
        assert delta_event.tool_call_id == "call_real"
