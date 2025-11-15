from agency_swarm.agent.execution_streaming import prune_guardrail_messages


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
    """
    Tree:
        CustomerSupportAgent (guardrail trips here)
        └── DatabaseAgent
            └── EmailAgent

    Guardrail fires before any delegation completes, so the history must collapse to the
    real user + the guardrail guidance from the root agent.
    """
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    guardrail_message = _build_message(
        role="assistant",
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

    pruned = prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, guardrail_message, unrelated_other_trace]


def test_prune_guardrail_messages_child_run_keeps_trigger_input_and_guidance() -> None:
    """
    Tree:
        CustomerSupportAgent
        └── DatabaseAgent (guardrail fires here)

    The DatabaseAgent's user prompt plus its guidance must remain so the parent knows what
    to fix, but any generated assistant outputs/function calls are trimmed.
    """
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    forwarded_input = _build_message(
        role="user",
        parent_run_id="call_child",
        agent_run_id="agent_run_child",
        caller_agent="ParentAgent",
    )
    guardrail_message = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id="call_child",
        agent_run_id="agent_run_child",
    )
    function_call = _build_message(
        role=None,
        parent_run_id="call_child",
        agent_run_id="agent_run_child",
        caller_agent="ParentAgent",
        extra={"type": "function_call"},
    )

    all_messages = [
        preserved_user,
        forwarded_input,
        guardrail_message,
        function_call,
    ]

    pruned = prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, forwarded_input, guardrail_message]


def test_prune_guardrail_messages_preserves_other_traces() -> None:
    """
    Tree:
        CustomerSupportAgent (affected trace)

    A parallel trace stays untouched even when the guardrail triggers for the trace under
    inspection.
    """
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    guardrail_message = _build_message(
        role="assistant",
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

    pruned = prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, guardrail_message, concurrent_message]


def test_prune_guardrail_messages_drops_no_op_trace_descendants() -> None:
    """
    Tree:
        ParentAgent
        └── HelperAgent (run_trace_id=no-op)

    HelperAgent belongs to a no-op trace branch, so it is removed even if it emitted
    assistant outputs before the guardrail fired elsewhere.
    """
    preserved_user = _build_message(role="user", parent_run_id=None, agent_run_id="agent_run_parent")
    guardrail_message = _build_message(
        role="assistant",
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

    pruned = prune_guardrail_messages(
        all_messages,
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [preserved_user, guardrail_message]


def test_prune_guardrail_messages_drops_nested_agent_user_and_errors() -> None:
    """
    Tree:
        CustomerSupportAgent
        └── DatabaseAgent
            └── EmailAgent (guardrail fires here, but parent guidance also added)

    Inter-agent *user* messages remain so the next retry has full context, while any
    assistant/system responses are scoped to the guardrail location.
    """
    real_user = _build_message(
        role="user",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        caller_agent=None,
        agent="CustomerSupportAgent",
    )
    db_user = _build_message(
        role="user",
        parent_run_id="call_db",
        agent_run_id="agent_run_db",
        caller_agent="CustomerSupportAgent",
        agent="DatabaseAgent",
    )
    email_user = _build_message(
        role="user",
        parent_run_id="call_email",
        agent_run_id="agent_run_email",
        caller_agent="DatabaseAgent",
        agent="EmailAgent",
    )
    email_guardrail_guidance = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id="call_email",
        agent_run_id="agent_run_email",
        caller_agent="DatabaseAgent",
        agent="EmailAgent",
    )
    db_guardrail_guidance = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id="call_db",
        agent_run_id="agent_run_db",
        caller_agent="CustomerSupportAgent",
        agent="DatabaseAgent",
    )
    top_guardrail_message = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        caller_agent=None,
        agent="CustomerSupportAgent",
    )

    pruned = prune_guardrail_messages(
        [
            real_user,
            db_user,
            email_user,
            email_guardrail_guidance,
            db_guardrail_guidance,
            top_guardrail_message,
        ],
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [
        real_user,
        db_user,
        email_user,
        email_guardrail_guidance,
        db_guardrail_guidance,
        top_guardrail_message,
    ]


def test_prune_guardrail_messages_preserves_parent_guidance_after_child_guardrail() -> None:
    """
    Tree:
        CustomerSupportAgent
        └── DatabaseAgent (guardrail fires here)

    Even when the child trips the guardrail, the parent agent receives its own guidance
    message that must remain in history so the user can see what to fix.
    """
    real_user = _build_message(
        role="user",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        caller_agent=None,
        agent="CustomerSupportAgent",
    )
    parent_prompt = _build_message(
        role="user",
        parent_run_id="call_db",
        agent_run_id="agent_run_db",
        caller_agent="CustomerSupportAgent",
        agent="DatabaseAgent",
    )
    db_guardrail_guidance = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id="call_db",
        agent_run_id="agent_run_db",
        caller_agent="CustomerSupportAgent",
        agent="DatabaseAgent",
    )
    parent_guidance = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        caller_agent=None,
        agent="CustomerSupportAgent",
    )

    pruned = prune_guardrail_messages(
        [real_user, parent_prompt, db_guardrail_guidance, parent_guidance],
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [real_user, parent_prompt, db_guardrail_guidance, parent_guidance]


def test_prune_guardrail_messages_keeps_child_guardrail_guidance_for_parent() -> None:
    """
    Tree:
        CustomerSupportAgent
        └── DatabaseAgent (guardrail fires here)

    Parent agent still needs to see the child guardrail guidance (callerAgent is set),
    otherwise replays would lack actionable detail.
    """
    real_user = _build_message(
        role="user",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        caller_agent=None,
        agent="CustomerSupportAgent",
    )
    db_prompt = _build_message(
        role="user",
        parent_run_id="call_db",
        agent_run_id="agent_run_db",
        caller_agent="CustomerSupportAgent",
        agent="DatabaseAgent",
    )
    db_guardrail_message = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id="call_db",
        agent_run_id="agent_run_db",
        caller_agent="CustomerSupportAgent",
        agent="DatabaseAgent",
    )

    pruned = prune_guardrail_messages(
        [real_user, db_prompt, db_guardrail_message],
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [real_user, db_prompt, db_guardrail_message]


def test_prune_guardrail_messages_drops_descendants_after_guardrail() -> None:
    """
    Tree:
        CustomerSupportAgent
        └── DatabaseAgent
            └── EmailAgent (guardrail fires here)
                └── HelperAgent (spawned after guardrail)

    Any further delegations triggered after the guardrail trips are removed to keep the
    tree consistent with the halted execution.
    """
    real_user = _build_message(
        role="user",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        caller_agent=None,
        agent="CustomerSupportAgent",
    )
    db_user = _build_message(
        role="user",
        parent_run_id="call_db",
        agent_run_id="agent_run_db",
        caller_agent="CustomerSupportAgent",
        agent="DatabaseAgent",
    )
    email_guardrail_guidance = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id="call_email",
        agent_run_id="agent_run_email",
        caller_agent="DatabaseAgent",
        agent="EmailAgent",
    )
    descendant_after_guardrail = _build_message(
        role="assistant",
        parent_run_id="call_followup",
        agent_run_id="agent_run_followup",
        caller_agent="EmailAgent",
        agent="HelperAgent",
    )
    parent_guidance = _build_message(
        role="assistant",
        message_origin="input_guardrail_message",
        parent_run_id=None,
        agent_run_id="agent_run_parent",
        caller_agent=None,
        agent="CustomerSupportAgent",
    )

    pruned = prune_guardrail_messages(
        [real_user, db_user, email_guardrail_guidance, descendant_after_guardrail, parent_guidance],
        initial_saved_count=1,
        run_trace_id="trace_guardrail",
    )

    assert pruned == [real_user, email_guardrail_guidance, parent_guidance]
