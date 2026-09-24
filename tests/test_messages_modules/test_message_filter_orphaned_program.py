"""Programmatic tool-call pairs must be stripped together from replayable histories.

OpenAI Responses programmatic tool calling emits a ``program`` item and a
``program_output`` item linked by ``call_id``. Replaying either side without its
partner violates the same call/output invariant as other paired tool items.
"""

from agency_swarm.messages.message_filter import MessageFilter


def _program(call_id: str = "call_1") -> dict[str, str]:
    return {
        "type": "program",
        "id": "prog_1",
        "call_id": call_id,
        "code": "return 1",
        "fingerprint": "fp_1",
    }


def _program_output(call_id: str = "call_1") -> dict[str, str]:
    return {
        "type": "program_output",
        "id": "out_1",
        "call_id": call_id,
        "result": "1",
        "status": "completed",
    }


def test_removes_program_without_output() -> None:
    assert MessageFilter.remove_orphaned_messages([_program()]) == []


def test_removes_program_output_without_program() -> None:
    assert MessageFilter.remove_orphaned_messages([_program_output()]) == []


def test_keeps_matched_program_pair() -> None:
    program = _program()
    output = _program_output()

    assert MessageFilter.remove_orphaned_messages([program, output]) == [program, output]
