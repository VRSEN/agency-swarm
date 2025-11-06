from agency_swarm.agent.execution_streaming import _prune_guardrail_messages


def _build_message(
    *,
    role: str | None,
    message_origin: str | None = None,
    parent_run_id: str | None = None,
    agent_run_id: str | None = None,
    run_trace_id: str = "trace_guardrail",
    caller_agent: str | None = None,
    agent: str | None = None,
    extra: dict | None = None,
) -> dict:
    msg = {
        "role": role,
        "message_origin": message_origin,
        "parent_run_id": parent_run_id,
        "agent_run_id": agent_run_id,
        "run_trace_id": run_trace_id,
        "callerAgent": caller_agent,
        "agent": agent,
        "type": "message",
    }
    if extra:
        msg.update(extra)
    return msg


def test_prune_guardrail_messages_parent_run_only_keeps_user_and_guidance() -> None:
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    guardrail_message = _build_message(
        role="system",
        message_origin="input_guardrail_message",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
    )
    to_remove_assistant = _build_message(role="assistant", parent_run_id=None, agent_run_id="agent_run_parent")
    unrelated_other_trace = _build_message(role="assistant", run_trace_id="trace_other")

    all_messages = [
        preserved_user,
        guardrail_message,
        to_remove_assistant,
        unrelated_other_trace,
    ]

    pruned = _prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, guardrail_message, unrelated_other_trace]


def test_prune_guardrail_messages_child_run_keeps_trigger_input_and_guidance() -> None:
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    forwarded_input = _build_message(
        role="user",
        parent_run_id="call_child",
        agent_run_id="agent_run_child",
    )
    guardrail_message = _build_message(
        role="system",
        message_origin="input_guardrail_message",
        parent_run_id="call_child",
        agent_run_id="agent_run_child",
    )
    function_call = _build_message(
        role=None,
        parent_run_id="call_child",
        agent_run_id="agent_run_child",
        extra={"type": "function_call"},
    )

    all_messages = [
        preserved_user,
        forwarded_input,
        guardrail_message,
        function_call,
    ]

    pruned = _prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, forwarded_input, guardrail_message]


def test_prune_guardrail_messages_preserves_other_traces() -> None:
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    guardrail_message = _build_message(
        role="system",
        message_origin="input_guardrail_message",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
    )
    concurrent_message = _build_message(
        role="assistant",
        parent_run_id=None,
        agent_run_id="agent_run_other",
        run_trace_id="trace_other",
    )

    all_messages = [
        preserved_user,
        guardrail_message,
        concurrent_message,
    ]

    pruned = _prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, guardrail_message, concurrent_message]


def test_prune_guardrail_messages_drops_no_op_trace_descendants() -> None:
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    guardrail_message = _build_message(
        role="system",
        message_origin="input_guardrail_message",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        agent="ParentAgent",
    )
    helper_assistant = _build_message(
        role="assistant",
        parent_run_id="call_send_message",
        agent_run_id="agent_run_helper",
        run_trace_id="no-op",
        caller_agent="ParentAgent",
        agent="HelperAgent",
    )

    all_messages = [
        preserved_user,
        guardrail_message,
        helper_assistant,
    ]

    pruned = _prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, guardrail_message]
