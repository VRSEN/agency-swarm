from typing import Any

from agents.models._openai_shared import get_default_openai_client
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils.override_policy import (
    _get_openai_client_from_agent,
    _get_upload_client_agent,
)
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

_CODEX_DEVELOPER_ROLE_PRESERVATION_ORIGINS = {
    "file_search_preservation",
    "web_search_preservation",
}


def prepare_chat_history_for_client_config(
    chat_history: list[dict[str, Any]],
    config: ClientConfig | None,
    agency: Agency | None = None,
    recipient_agent: str | None = None,
) -> list[dict[str, Any]]:
    """Return request chat history adjusted for the active backend compatibility boundary."""
    if not _uses_codex_backend(config, agency, recipient_agent=recipient_agent):
        return chat_history

    prepared_history: list[dict[str, Any]] = []
    for item in chat_history:
        if item.get("role") == "system" and item.get("message_origin") in _CODEX_DEVELOPER_ROLE_PRESERVATION_ORIGINS:
            item = {**item, "role": "developer"}
        prepared_history.append(item)
    return prepared_history


def prepare_loaded_chat_history_for_active_client(
    agency: Agency,
    chat_history: list[dict[str, Any]] | None,
    config: ClientConfig | None,
    recipient_agent: str | None = None,
) -> None:
    """Update loaded request chat history after agency/request clients have been resolved."""
    if chat_history is None:
        return
    thread_manager = getattr(agency, "thread_manager", None)
    replace_messages = getattr(thread_manager, "replace_messages", None)
    if not callable(replace_messages):
        return
    replace_messages(
        prepare_chat_history_for_client_config(
            chat_history,
            config,
            agency=agency,
            recipient_agent=recipient_agent,
        )
    )


def _uses_codex_backend(
    config: ClientConfig | None,
    agency: Agency | None = None,
    recipient_agent: str | None = None,
) -> bool:
    """Return True when the resolved request backend is Codex browser auth."""
    if config is not None and config.base_url is not None:
        return _is_codex_base_url(config.base_url)

    if agency is not None:
        selected_agent = _get_upload_client_agent(agency, recipient_agent=recipient_agent)
        if selected_agent is not None:
            agent_uses_codex = _agent_codex_backend_state(selected_agent)
            if agent_uses_codex is not None:
                return agent_uses_codex

    return _client_uses_codex_backend(get_default_openai_client())


def _agent_codex_backend_state(agent: Agent) -> bool | None:
    client = _get_openai_client_from_agent(agent)
    if client is not None:
        return _client_uses_codex_backend(client)
    cached_client = getattr(agent, "_openai_client", None)
    if isinstance(cached_client, AsyncOpenAI):
        return _client_uses_codex_backend(cached_client)
    return None


def _client_uses_codex_backend(client: AsyncOpenAI | None) -> bool:
    if client is None:
        return False
    return _is_codex_base_url(str(client.base_url))


def _is_codex_base_url(value: str | None) -> bool:
    if not value:
        return False
    return value.rstrip("/") == "https://chatgpt.com/backend-api/codex"
