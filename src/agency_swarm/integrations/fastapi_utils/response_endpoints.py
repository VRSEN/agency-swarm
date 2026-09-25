"""Non-streaming response, metadata, logs and chat-name endpoint factories."""

import logging
from collections.abc import Callable, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any, cast

from agents import ModelSettings, OpenAIResponsesModel, TResponseInputItem, output_guardrail
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
from openai.types.shared.reasoning import Reasoning
from pydantic import BaseModel, Field

from agency_swarm import Agency, Agent, GuardrailFunctionOutput, RunContextWrapper
from agency_swarm.agent.constants import FRAMEWORK_DEFAULT_MODEL
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.logging_middleware import get_logs_endpoint_impl
from agency_swarm.integrations.fastapi_utils.message_builders import (
    _build_chat_name_messages,
    _build_message_with_file_urls_context,
    _normalize_new_messages_for_client,
)
from agency_swarm.integrations.fastapi_utils.oauth_helpers import (
    _clear_oauth_request_context,
    _ensure_request_oauth_config,
    _has_oauth_servers,
    _no_oauth_user_id,
    _requires_oauth_agent_state_restore,
    _resolve_oauth_user_id,
    _with_oauth_user_context,
)
from agency_swarm.integrations.fastapi_utils.oauth_support import (
    FastAPIOAuthConfig,
    FastAPIOAuthRuntime,
    has_hosted_mcp_tools_missing_authorization,
)
from agency_swarm.integrations.fastapi_utils.override_policy import (
    RequestOverridePolicy,
    get_allowed_dirs_for_metadata,
)
from agency_swarm.integrations.fastapi_utils.override_session import _RequestOverrideSession
from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.messages.codex_input import (
    is_codex_base_url as _is_codex_base_url,
    rewrite_system_input_roles_for_codex,
)
from agency_swarm.messages.response_input_sanitizer import (
    REASONING_ENCRYPTED_CONTENT_INCLUDE,
    sanitize_store_false_responses_input,
)
from agency_swarm.utils.dry_run import force_dry_run
from agency_swarm.utils.usage_tracking import (
    calculate_usage_with_cost,
    extract_usage_from_run_result,
)

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


# Non‑streaming response endpoint
def make_response_endpoint(
    request_model,
    agency_factory: Callable[..., Agency],
    verify_token,
    allowed_local_dirs: Sequence[str | Path] | None = None,
    oauth_config: FastAPIOAuthConfig | None = None,
):
    user_id_dependency = oauth_config.user_id_dependency if oauth_config else _no_oauth_user_id

    async def handler(
        request: request_model,
        token: str = Depends(verify_token),
        user_id: object = Depends(user_id_dependency),
    ):
        user_id = _resolve_oauth_user_id(user_id, oauth_config)
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        oauth_runtime = None
        if oauth_config:
            oauth_runtime = FastAPIOAuthRuntime(
                oauth_config.registry,
                user_id,
                timeout=oauth_config.timeout,
                enable_hosted_mcp_oauth=oauth_config.enable_hosted_mcp_oauth,
            )

        agency_instance = agency_factory(load_threads_callback=load_callback)
        _ensure_request_oauth_config(agency_instance, oauth_config)
        request_user_context = _with_oauth_user_context(request.user_context, user_id)
        override_policy = RequestOverridePolicy(request.client_config)
        override_session = _RequestOverrideSession(
            agency=agency_instance,
            policy=override_policy,
            restore_oauth_state=_requires_oauth_agent_state_restore(agency_instance, oauth_runtime),
        )
        request_upload_client: AsyncOpenAI | None = None

        combined_file_ids = request.file_ids
        file_ids_map = None
        message_input: str | list[TResponseInputItem] = request.message

        try:
            await override_session.acquire()
            oauth_runtime = endpoint_handlers._prepare_oauth_runtime(agency_instance, oauth_runtime, user_id)

            has_hosted_mcp_oauth = (
                oauth_config is not None
                and oauth_config.enable_hosted_mcp_oauth
                and has_hosted_mcp_tools_missing_authorization(agency_instance)
            )
            if oauth_runtime and (_has_oauth_servers(agency_instance) or has_hosted_mcp_oauth):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "OAuth-enabled MCP servers and hosted MCP tools require "
                        "/get_response_stream for redirect events"
                    ),
                )

            request_upload_client = endpoint_handlers._build_file_upload_client(
                agency_instance,
                request.client_config,
                recipient_agent=request.recipient_agent,
            )

            if request.file_urls is not None:
                try:
                    file_ids_map = await endpoint_handlers.upload_from_urls(
                        request.file_urls,
                        allowed_local_dirs=allowed_local_dirs,
                        openai_client=request_upload_client,
                    )
                    combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
                    message_input = _build_message_with_file_urls_context(
                        request.message,
                        request.file_urls,
                        file_ids_map,
                    )
                except Exception as e:
                    return {"error": f"Error downloading file from provided urls: {e}"}

            # Attach persistent MCP servers and ensure connections before handling the request
            await endpoint_handlers.attach_persistent_mcp_servers(agency_instance)

            # Capture initial message count to identify new messages
            initial_message_count = len(agency_instance.thread_manager.get_all_messages())

            response = await agency_instance.get_response(
                message=message_input,
                recipient_agent=request.recipient_agent,
                context_override=request_user_context,
                additional_instructions=request.additional_instructions,
                file_ids=combined_file_ids,
            )
            # Get only new messages added during this request
            all_messages = agency_instance.thread_manager.get_all_messages()
            new_messages = all_messages[initial_message_count:]  # Only messages added during this request
            filtered_messages = MessageFilter.filter_messages(new_messages)
            filtered_messages = _normalize_new_messages_for_client(filtered_messages)
            result = {"response": response.final_output, "new_messages": filtered_messages}

            # Extract and add usage information
            usage_stats = extract_usage_from_run_result(response)
            if usage_stats:
                # Calculate cost - model_name is auto-extracted from run_result._main_agent_model
                usage_stats = calculate_usage_with_cost(usage_stats, run_result=response)
                result["usage"] = usage_stats.to_dict()

            if request.file_urls is not None and file_ids_map is not None:
                result["file_ids_map"] = file_ids_map
            if request.generate_chat_name:
                try:
                    result["chat_name"] = await endpoint_handlers.generate_chat_name(
                        _build_chat_name_messages(filtered_messages),
                        openai_client=request_upload_client,
                    )
                except Exception as e:
                    # Do not add errors to the result as they might be mistaken for chat name
                    logger.error(f"Error generating chat name: {e}")
            return result
        finally:
            await override_session.cleanup()
            _clear_oauth_request_context()

    return handler


def make_metadata_endpoint(
    agency_factory: Callable[..., Agency],
    verify_token,
    allowed_local_dirs: Sequence[str | Path] | None = None,
):
    async def handler(token: str = Depends(verify_token)):
        # Metadata must reflect current factory state for /connect and agent
        # selection flows; a startup snapshot goes stale.
        with force_dry_run():
            preview_instance = agency_factory(load_threads_callback=lambda: [])
            agents_map = getattr(preview_instance, "agents", None)
            if isinstance(agents_map, dict):
                for agent in agents_map.values():
                    ensure_mcp_tools = getattr(agent, "ensure_mcp_tools", None)
                    if callable(ensure_mcp_tools):
                        ensure_mcp_tools()
            agency_metadata = preview_instance.get_metadata()
        metadata_with_version = dict(agency_metadata)
        agency_swarm_version = endpoint_handlers._get_agency_swarm_version()
        if agency_swarm_version is not None:
            metadata_with_version["agency_swarm_version"] = agency_swarm_version
        # Always include so clients can tell if local file access is enabled and what paths are allowed.
        if allowed_local_dirs is None:
            metadata_with_version["allowed_local_file_dirs"] = None
        else:
            metadata_with_version["allowed_local_file_dirs"] = get_allowed_dirs_for_metadata(allowed_local_dirs)
        return metadata_with_version

    return handler


def make_logs_endpoint(request_model, logs_dir: str, verify_token):
    """Create a logs endpoint handler following the same pattern as other endpoints."""

    async def handler(request: request_model, token: str = Depends(verify_token)):
        return await get_logs_endpoint_impl(request.log_id, logs_dir)

    return handler


async def exception_handler(request, exc):
    error_message = str(exc)
    if isinstance(exc, tuple):
        error_message = str(exc[1]) if len(exc) > 1 else str(exc[0])
    return JSONResponse(status_code=500, content={"error": error_message})


async def generate_chat_name(
    new_messages: list[TResponseInputItem],
    openai_client: AsyncOpenAI | None = None,
):
    client = openai_client or endpoint_handlers.get_default_openai_client() or AsyncOpenAI()

    def _word_count(value: str) -> int:
        return len(value.split(" "))

    class ResponseFormat(BaseModel):
        chat_name: str = Field(description="A fitting name for the provided chat history.")

    @output_guardrail  # type: ignore[arg-type]
    async def response_content_guardrail(
        context: RunContextWrapper, agent: Agent, response_text: str | type[BaseModel]
    ) -> GuardrailFunctionOutput:
        tripwire_triggered = False
        output_info = ""

        chat_name = response_text.chat_name if isinstance(response_text, ResponseFormat) else str(response_text)

        if _word_count(chat_name) < 2 or _word_count(chat_name) > 6:
            tripwire_triggered = True
            output_info = "The name should contain between 2 and 6 words"

        return GuardrailFunctionOutput(
            output_info=output_info,
            tripwire_triggered=tripwire_triggered,
        )

    stripped_messages = MessageFormatter.strip_agency_metadata(new_messages)  # type: ignore[arg-type]
    formatted_messages = str(stripped_messages)
    if len(formatted_messages) > 1000:
        formatted_messages = "HISTORY TRUNCATED TO 1000 CHARACTERS:\n" + formatted_messages[:1000]

    title_instructions = """
You are a helpful assistant that generates a human-friendly title for a conversation.
You will receive a list of messages where the first one is the user input and the rest are
related to the assistant response.
Rules:
- Prioritize the user's first message; use later turns only to disambiguate
- 2-6 words, Title Case
- No punctuation except spaces; no emojis, quotes, model/tool names, or trailing period
- Output only the title text (no explanations)
- If the first user message is generic (e.g., “hi”), use the best available intent from the rest of the messages.
- If you lack context of the user input (continuation of an ongoing conversation), derive it from agent's response.
"""

    if _is_codex_base_url(str(client.base_url)):
        codex_input: list[TResponseInputItem]
        if len(formatted_messages) > 1000:
            codex_input = [cast(TResponseInputItem, {"role": "user", "content": formatted_messages})]
        else:
            codex_input = cast(list[TResponseInputItem], stripped_messages)
            codex_input = cast(list[TResponseInputItem], sanitize_store_false_responses_input(codex_input))
        codex_input = cast(
            list[TResponseInputItem],
            rewrite_system_input_roles_for_codex(cast(list[dict[str, Any]], codex_input)),
        )

        retry_suffix = ""
        for _attempt in range(4):
            response = cast(
                Any,
                await client.responses.create(
                    model=FRAMEWORK_DEFAULT_MODEL,
                    instructions=title_instructions + retry_suffix,
                    input=codex_input,
                    include=[REASONING_ENCRYPTED_CONTENT_INCLUDE],
                    store=False,
                    stream=True,
                    reasoning={"effort": "none"},
                ),
            )
            text_parts: list[str] = []
            async for event in response:
                if getattr(event, "type", "") != "response.output_text.delta":
                    continue
                delta = getattr(event, "delta", None)
                if isinstance(delta, str) and delta:
                    text_parts.append(delta)
            chat_name = "".join(text_parts).strip()
            if 2 <= _word_count(chat_name) <= 6:
                return chat_name
            retry_suffix = (
                "\nThe previous title was invalid because it must contain between 2 and 6 words. "
                "Return a corrected title now."
            )
        raise ValueError("Generated chat name must contain between 2 and 6 words")

    model = OpenAIResponsesModel(model=FRAMEWORK_DEFAULT_MODEL, openai_client=client)

    name_agent = Agent(
        name="NameGenerator",
        model=model,
        model_settings=ModelSettings(store=False, reasoning=Reasoning(effort="none")),
        instructions=title_instructions,
        output_type=ResponseFormat,
        validation_attempts=3,
        output_guardrails=[response_content_guardrail],
    )

    agency = Agency(name_agent)
    run_result = await agency.get_response(formatted_messages)
    return run_result.final_output.chat_name


def _get_agency_swarm_version() -> str | None:
    """Return the installed agency-swarm version, if available."""

    try:
        return metadata.version("agency-swarm")
    except metadata.PackageNotFoundError:
        logger.debug("agency-swarm package metadata not found; returning no version")
        return None
