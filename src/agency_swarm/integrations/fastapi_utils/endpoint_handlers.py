import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from importlib import metadata

from ag_ui.core import EventType, MessagesSnapshotEvent, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.encoder import EventEncoder
from agents import OpenAIResponsesModel, TResponseInputItem, output_guardrail
from agents.exceptions import OutputGuardrailTripwireTriggered
from agents.models._openai_shared import get_default_openai_client
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from agency_swarm import (
    Agency,
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
)
from agency_swarm.integrations.fastapi_utils.file_handler import upload_from_urls
from agency_swarm.integrations.fastapi_utils.logging_middleware import get_logs_endpoint_impl
from agency_swarm.messages import MessageFilter
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers
from agency_swarm.ui.core.agui_adapter import AguiAdapter, serialize

logger = logging.getLogger(__name__)


def _get_agency_swarm_version() -> str | None:
    """Return the installed agency-swarm version, if available."""

    try:
        return metadata.version("agency-swarm")
    except metadata.PackageNotFoundError:
        logger.debug("agency-swarm package metadata not found; returning no version")
        return None


def get_verify_token(app_token):
    auto_error = app_token is not None and app_token != ""
    security = HTTPBearer(auto_error=auto_error)

    async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):  # noqa: B008
        if app_token is None or app_token == "":
            return None
        if not credentials or credentials.credentials != app_token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return credentials.credentials

    return verify_token


# Non‑streaming response endpoint
def make_response_endpoint(request_model, agency_factory: Callable[..., Agency], verify_token):
    async def handler(request: request_model, token: str = Depends(verify_token)):
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        combined_file_ids = request.file_ids
        file_ids_map = None
        if request.file_urls is not None:
            try:
                file_ids_map = await upload_from_urls(request.file_urls)
                combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
            except Exception as e:
                return {"error": f"Error downloading file from provided urls: {e}"}

        agency_instance = agency_factory(load_threads_callback=load_callback)
        # Attach persistent MCP servers and ensure connections before handling the request
        await attach_persistent_mcp_servers(agency_instance)

        # Capture initial message count to identify new messages
        initial_message_count = len(agency_instance.thread_manager.get_all_messages())

        response = await agency_instance.get_response(
            message=request.message,
            recipient_agent=request.recipient_agent,
            additional_instructions=request.additional_instructions,
            file_ids=combined_file_ids,
        )
        # Get only new messages added during this request
        all_messages = agency_instance.thread_manager.get_all_messages()
        new_messages = all_messages[initial_message_count:]  # Only messages added during this request
        filtered_messages = MessageFilter.filter_messages(new_messages)
        result = {"response": response.final_output, "new_messages": filtered_messages}
        if request.file_urls is not None and file_ids_map is not None:
            result["file_ids_map"] = file_ids_map
        if request.generate_chat_name:
            try:
                result["chat_name"] = await generate_chat_name(filtered_messages)
            except Exception as e:
                # Do not add errors to the result as they might be mistaken for chat name
                logger.error(f"Error generating chat name: {e}")
        return result

    return handler


# Streaming SSE endpoint
def make_stream_endpoint(request_model, agency_factory: Callable[..., Agency], verify_token):
    async def handler(request: request_model, token: str = Depends(verify_token)):
        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history
        else:

            def load_callback() -> list:
                return []

        combined_file_ids = request.file_ids
        file_ids_map = None
        if request.file_urls is not None:
            try:
                file_ids_map = await upload_from_urls(request.file_urls)
                combined_file_ids = (combined_file_ids or []) + list(file_ids_map.values())
            except Exception as e:
                error_msg = str(e)

                async def error_generator():
                    yield (
                        "data: "
                        + json.dumps({"error": f"Error downloading file from provided urls: {error_msg}"})
                        + "\n\n"
                    )
                    yield "event: end\ndata: [DONE]\n\n"

                return StreamingResponse(
                    error_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )

        agency_instance = agency_factory(load_threads_callback=load_callback)
        await attach_persistent_mcp_servers(agency_instance)

        async def event_generator():
            # Capture initial message count to identify new messages
            initial_message_count = len(agency_instance.thread_manager.get_all_messages())

            try:
                async for event in agency_instance.get_response_stream(
                    message=request.message,
                    recipient_agent=request.recipient_agent,
                    additional_instructions=request.additional_instructions,
                    file_ids=combined_file_ids,
                ):
                    try:
                        data = serialize(event)
                        yield "data: " + json.dumps({"data": data}) + "\n\n"
                    except Exception as e:
                        yield "data: " + json.dumps({"error": f"Failed to serialize event: {e}"}) + "\n\n"
            except Exception as exc:
                if isinstance(exc, OutputGuardrailTripwireTriggered):
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "error": "Guardrail OutputGuardrail triggered tripwire: "
                                + str(exc.guardrail_result.output.output_info)
                            }
                        )
                        + "\n\n"
                    )
                else:
                    yield "data: " + json.dumps({"error": str(exc)}) + "\n\n"

            # Get only new messages added during this request
            all_messages = agency_instance.thread_manager.get_all_messages()
            new_messages = all_messages[initial_message_count:]  # Only messages added during this request
            # Preserve agent_run_id grouping for UI correlation
            filtered_messages = MessageFilter.filter_messages(new_messages)
            result = {"new_messages": filtered_messages}
            if request.file_urls is not None and file_ids_map is not None:
                result["file_ids_map"] = file_ids_map
            if request.generate_chat_name:
                try:
                    result["chat_name"] = await generate_chat_name(filtered_messages)
                except Exception as e:
                    # Do not add errors to the result as they might be mistaken for chat name
                    logger.error(f"Error generating chat name: {e}")
            yield "event: messages\ndata: " + json.dumps(result) + "\n\n"

            # explicit terminator
            yield "event: end\ndata: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return handler


# Tool endpoint
def make_tool_endpoint(tool, verify_token, context=None):
    async def handler(request: Request, token: str = Depends(verify_token)):
        try:
            data = await request.json()
            # If this is a FunctionTool (from @function_tool), use on_invoke_tool
            if hasattr(tool, "on_invoke_tool"):
                input_json = json.dumps(data)
                result = await tool.on_invoke_tool(context, input_json)
            elif isinstance(tool, type):
                tool_instance = tool(**data)
                result = tool_instance.run()
                if asyncio.iscoroutine(result):
                    result = await result
            else:
                result = tool(**data)
                if asyncio.iscoroutine(result):
                    result = await result
            return {"response": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"Error": str(e)})

    return handler


def make_agui_chat_endpoint(request_model, agency_factory: Callable[..., Agency], verify_token):
    async def handler(request: request_model, token: str = Depends(verify_token)):
        """Accepts AG-UI `RunAgentInput`, returns an AG-UI event stream."""

        encoder = EventEncoder()

        if request.chat_history is not None:
            # Chat history is now a flat list
            def load_callback() -> list:
                return request.chat_history

        elif request.messages is not None:
            # Pull the default agent from the agency
            agency = agency_factory()
            default_agent = agency.entry_points[0]

            # Convert AG-UI messages to flat chat history with metadata
            def load_callback() -> list:
                agui_messages = AguiAdapter.agui_messages_to_chat_history(request.messages)
                # Add agency metadata to each message
                for msg in agui_messages:
                    if "agent" not in msg:
                        msg["agent"] = default_agent.name
                    if "callerAgent" not in msg:
                        msg["callerAgent"] = None
                    if "timestamp" not in msg:
                        msg["timestamp"] = int(time.time() * 1000)
                return agui_messages

        else:

            def load_callback() -> list:
                return []

        # Choose / build an agent – here we just create a demo agent each time.
        agency = agency_factory(load_threads_callback=load_callback)
        await attach_persistent_mcp_servers(agency)

        async def event_generator() -> AsyncGenerator[str]:
            # Emit RUN_STARTED first.
            yield encoder.encode(
                RunStartedEvent(
                    type=EventType.RUN_STARTED,
                    thread_id=request.thread_id,
                    run_id=request.run_id,
                )
            )

            try:
                # Create AguiAdapter instance with clean state for this request
                agui_adapter = AguiAdapter()

                # Store in dict format to avoid converting to classes
                snapshot_messages = [message.model_dump() for message in request.messages]
                async for event in agency.get_response_stream(
                    message=request.messages[-1].content,
                    additional_instructions=request.additional_instructions,
                ):
                    agui_event = agui_adapter.openai_to_agui_events(
                        event,
                        run_id=request.run_id,
                    )
                    if agui_event:
                        events = agui_event if isinstance(agui_event, list) else [agui_event]
                        for event in events:
                            if isinstance(event, MessagesSnapshotEvent):
                                snapshot_messages.append(event.messages[0].model_dump())
                                yield encoder.encode(
                                    MessagesSnapshotEvent(type=EventType.MESSAGES_SNAPSHOT, messages=snapshot_messages)
                                )
                            else:
                                yield encoder.encode(event)

                yield encoder.encode(
                    RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=request.thread_id,
                        run_id=request.run_id,
                    )
                )

            except Exception as exc:
                import traceback

                # Surface error as AG-UI event so the frontend can react.
                tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                error_message = f"{str(exc)}\n\nTraceback:\n{tb_str}"
                yield encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=error_message))

        return StreamingResponse(event_generator(), media_type=encoder.get_content_type())

    return handler


def make_metadata_endpoint(agency_metadata: dict, verify_token):
    async def handler(token: str = Depends(verify_token)):
        metadata_with_version = dict(agency_metadata)
        agency_swarm_version = _get_agency_swarm_version()
        if agency_swarm_version is not None:
            metadata_with_version["agency_swarm_version"] = agency_swarm_version
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


async def generate_chat_name(new_messages: list[TResponseInputItem]):
    client = get_default_openai_client() or AsyncOpenAI()

    class ResponseFormat(BaseModel):
        chat_name: str = Field(description="A fitting name for the provided chat history.")

    @output_guardrail  # type: ignore[arg-type]
    async def response_content_guardrail(
        context: RunContextWrapper, agent: Agent, response_text: str | type[BaseModel]
    ) -> GuardrailFunctionOutput:
        tripwire_triggered = False
        output_info = ""

        chat_name = response_text.chat_name if isinstance(response_text, ResponseFormat) else str(response_text)

        if len(chat_name.split(" ")) < 2 or len(chat_name.split(" ")) > 6:
            tripwire_triggered = True
            output_info = "The name should contain between 2 and 6 words"

        return GuardrailFunctionOutput(
            output_info=output_info,
            tripwire_triggered=tripwire_triggered,
        )

    from agency_swarm.messages import MessageFormatter

    formatted_messages = str(MessageFormatter.strip_agency_metadata(new_messages))  # type: ignore[arg-type]
    if len(formatted_messages) > 1000:
        formatted_messages = "HISTORY TRUNCATED TO 1000 CHARACTERS:\n" + formatted_messages[:1000]

    model = OpenAIResponsesModel(model="gpt-5-nano", openai_client=client)

    name_agent = Agent(
        name="NameGenerator",
        model=model,
        instructions=(
            """
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
        ),
        output_type=ResponseFormat,
        validation_attempts=3,
        output_guardrails=[response_content_guardrail],
    )

    agency = Agency(name_agent)

    response = await agency.get_response(formatted_messages)

    return response.final_output.chat_name
