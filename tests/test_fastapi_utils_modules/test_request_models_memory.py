from __future__ import annotations

from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest


def test_base_request_accepts_flat_memory_ids_without_touching_user_context() -> None:
    request = BaseRequest.model_validate(
        {
            "message": "hello",
            "user_context": {"theme": "dark"},
            "user_id": "user-1",
            "session_id": "chat-1",
        }
    )

    assert request.user_context == {"theme": "dark"}
    assert request.user_id == "user-1"
    assert request.session_id == "chat-1"


def test_base_request_accepts_advanced_memory_identity_without_touching_user_context() -> None:
    request = BaseRequest.model_validate(
        {
            "message": "hello",
            "user_context": {"theme": "dark"},
            "memory_identity": {"user_id": "user-1", "agency_id": "agency-1"},
        }
    )

    assert request.user_context == {"theme": "dark"}
    assert request.memory_identity is not None
    assert request.memory_identity.user_id == "user-1"
    assert request.memory_identity.agency_id == "agency-1"
