import asyncio
import inspect
import json
from collections.abc import AsyncGenerator, Callable
from typing import Any, TypeVar

from ag_ui.core import EventType, MessagesSnapshotEvent, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.core.types import Message
from ag_ui.encoder import EventEncoder
from agents.tool import FunctionTool, ToolContext
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agency_swarm.agency import Agency
from agency_swarm.agent import Agent
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, RunAgentInputCustom
from agency_swarm.ui.core.converters import AguiAdapter, serialize

BaseModelType = TypeVar("BaseModelType", bound=BaseModel)
BaseRequestType = TypeVar("BaseRequestType", bound=BaseRequest)
RunAgentInputType = TypeVar("RunAgentInputType", bound=RunAgentInputCustom)


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


def _arg_names(func: Callable) -> list[str]:
    return [param.name for param in inspect.signature(func).parameters.values()]


def _resolve_recipient_agent(
    agency_instance: Agency,
    request: BaseRequestType | RunAgentInputType | None = None,
    kwargs: dict[str, Any] | None = None,
) -> Agent:
    """
    Resolve the recipient agent for the given request and/or kwargs (or default to first entry point).
    """
    if request and hasattr(request, "recipient_agent"):
        return agency_instance._resolve_recipient_agent(request.recipient_agent)
    elif kwargs and "recipient_agent" in kwargs:
        return agency_instance._resolve_recipient_agent(kwargs["recipient_agent"])
    else:
        return agency_instance._resolve_recipient_agent()


def _kwargs_for(
    funcs: list[Callable],
    request: BaseRequestType | None = None,
    kwargs: dict[str, Any] | None = None,
    additional_kwargs: list[str] | None = None,
) -> dict[str, Any]:
    """
    Resolve the kwargs that exist in any of the given functions AND request and/or kwargs.
    Optionally add additional kwargs.
    """
    arg_names = list(set([arg_name for func in funcs for arg_name in _arg_names(func)]))
    if additional_kwargs:
        arg_names.extend(additional_kwargs)
    ret = {}
    if request:
        ret.update({key: value for key, value in request.model_dump(exclude_unset=True).items() if key in arg_names})
    if kwargs:
        ret.update({key: value for key, value in kwargs.items() if key in arg_names})
    return ret


def make_fastapi_response_endpoint(
    agency_factory: Callable[..., Agency], request_model: type[BaseRequestType] = BaseRequest
):
    """
    Factory for a generic FastAPI endpoint handlery.

    Parameters:
        agency_factory: The agency factory to use for the endpoint.
        request_model: The request model to use for the endpoint. Defaults to BaseRequest.

    Returns:
        A FastAPI endpoint handler that returns a synchronous response from the given agency.
    """

    async def handler(request: request_model, **kwargs):
        if request.chat_history is not None:
            chat_history_dict = {}
            for key, value in request.chat_history.items():
                chat_history_dict[key] = json.loads(value.model_dump_json())

            def load_callback() -> dict:
                return chat_history_dict

        else:

            def load_callback() -> dict:
                return {}

        agency_instance = agency_factory(load_threads_callback=load_callback)

        target_agent = _resolve_recipient_agent(agency_instance, request, kwargs)

        get_response_kwargs = _kwargs_for(
            funcs=[agency_instance.get_response, target_agent.get_response],
            request=request,
            kwargs=kwargs,
            additional_kwargs=["max_turns"],
        )

        response = await agency_instance.get_response(
            **get_response_kwargs,
        )
        history = {
            thread_id: {"items": thread.items, "metadata": thread.metadata}
            for thread_id, thread in agency_instance.thread_manager._threads.items()
        }
        return {"response": response.final_output, "chat_history": history}

    return handler


# Non‑streaming response endpoint
def make_response_endpoint(request_model, agency_factory: Callable[..., Agency], verify_token):
    """
    Legacy endpoint handler with a required verify_token dependency.
    """
    generic_handler = make_fastapi_response_endpoint(agency_factory, request_model)

    async def handler(request: request_model, token: str = Depends(verify_token)):
        ret = await generic_handler(request)
        return ret

    return handler


def make_stream_event_generator(agency_instance: Agency, **kwargs):
    """
    Factory for creating a generator that yields OpenAI-compatible streaming events for the given agency.

    Parameters:
        agency_instance: The agency instance to use for the endpoint.
        kwargs: Additional kwargs to pass to the endpoint. Will be passed to the agency's get_response_stream method.

    Returns:
        A generator that yields OpenAI-compatible streaming events for the given agency.
    """

    async def event_generator():
        try:
            target_agent = _resolve_recipient_agent(agency_instance, kwargs=kwargs)
            get_response_stream_kwargs = _kwargs_for(
                funcs=[agency_instance.get_response_stream, target_agent.get_response_stream],
                kwargs=kwargs,
                additional_kwargs=["max_turns"],
            )
            async for event in agency_instance.get_response_stream(
                **get_response_stream_kwargs,
            ):
                try:
                    data = serialize(event)
                    yield "data: " + json.dumps({"data": data}) + "\n\n"
                except Exception as e:
                    yield "data: " + json.dumps({"error": f"Failed to serialize event: {e}"}) + "\n\n"
        except Exception as exc:
            yield "data: " + json.dumps({"error": str(exc)}) + "\n\n"

        history = {
            thread_id: {"items": thread.items, "metadata": thread.metadata}
            for thread_id, thread in agency_instance.thread_manager._threads.items()
        }
        yield "data: " + json.dumps({"chat_history": history}) + "\n\n"

    return event_generator


def make_fastapi_stream_endpoint(
    agency_factory: Callable[..., Agency],
    request_model: type[BaseRequestType] = BaseRequest,
):
    """
    Factory for a FastAPI endpoint handler that returns a streaming response from the given agency.

    Parameters:
        agency_factory: The agency factory to use for the endpoint.
        request_model: The request model to use for the endpoint. Defaults to BaseRequest.

    Returns:
        A FastAPI endpoint handler that returns a streaming response from the given agency.
    """

    async def handler(request: request_model, **kwargs):
        if request.chat_history is not None:
            chat_history_dict = {}
            for key, value in request.chat_history.items():
                chat_history_dict[key] = json.loads(value.model_dump_json())

            def load_callback() -> dict:
                return chat_history_dict

        else:

            def load_callback() -> dict:
                return {}

        agency_instance = agency_factory(load_threads_callback=load_callback)

        event_generator = make_stream_event_generator(
            agency_instance, **request.model_dump(exclude_unset=True), **kwargs
        )

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


# Streaming SSE endpoint
def make_stream_endpoint(request_model: type[BaseRequestType], agency_factory: Callable[..., Agency], verify_token):
    """
    Legacy streaming endpoint handler with a required verify_token dependency.
    """
    generic_handler = make_fastapi_stream_endpoint(agency_factory, request_model)

    async def handler(request: request_model, token: str = Depends(verify_token)):
        ret = await generic_handler(request)
        return ret

    return handler


def make_fastapi_tool_endpoint(tool: FunctionTool, context: ToolContext[Any] | None = None):
    """
    Factory for a FastAPI endpoint handler that returns a response from the given tool.

    Parameters:
        tool: The tool to use for the endpoint.
        context: The context to use for the endpoint. Defaults to None.

    Returns:
        A FastAPI endpoint handler that returns a response from the given tool.
    """

    async def handler(request: Request):
        try:
            data = await request.json()
            # If this is a FunctionTool (from @function_tool), use on_invoke_tool
            if hasattr(tool, "on_invoke_tool"):
                # Ensure 'args' key is present for function tools
                if "args" not in data:
                    input_json = json.dumps({"args": data})
                else:
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


# Tool endpoint
def make_tool_endpoint(tool: FunctionTool, verify_token, context: ToolContext[Any] | None = None):
    """
    Legacy tool endpoint handler with a required verify_token dependency.
    """
    generic_handler = make_fastapi_tool_endpoint(tool, context)

    async def handler(request: Request, token: str = Depends(verify_token)):
        ret = await generic_handler(request)
        return ret

    return handler


def agui_event_generator(
    agency_instance: Agency, thread_id: str, run_id: str, messages: list[Message], **kwargs
) -> tuple[AsyncGenerator[str], EventEncoder]:
    """
    Make a generator that yields AG-UI events for the given agency.

    Parameters:
        agency_instance: The agency instance to use for the endpoint.
        thread_id: The thread ID to use for the endpoint.
        run_id: The run ID to use for the endpoint.
        messages: The messages to use for the endpoint.
        kwargs: Additional kwargs to pass to the endpoint. Will be passed to the agency's get_response_stream method.
    """
    encoder = EventEncoder()

    async def event_generator() -> AsyncGenerator[str]:
        # Emit RUN_STARTED first.
        yield encoder.encode(
            RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=thread_id,
                run_id=run_id,
            )
        )

        try:
            # Store in dict format to avoid converting to classes
            snapshot_messages = [message.model_dump() for message in messages]

            target_agent = _resolve_recipient_agent(agency_instance, kwargs=kwargs)
            get_response_stream_kwargs = _kwargs_for(
                funcs=[agency_instance.get_response_stream, target_agent.get_response_stream],
                kwargs=kwargs,
                additional_kwargs=["max_turns"],
            )

            async for event in agency_instance.get_response_stream(
                message=messages[-1].content,
                **get_response_stream_kwargs,
            ):
                agui_event = AguiAdapter.openai_to_agui_events(
                    event,
                    run_id=run_id,
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
                    thread_id=thread_id,
                    run_id=run_id,
                )
            )

        except Exception as exc:
            import traceback

            # Surface error as AG-UI event so the frontend can react.
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            error_message = f"{str(exc)}\n\nTraceback:\n{tb_str}"
            yield encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=error_message))

    return event_generator, encoder


def make_fastapi_agui_chat_endpoint(
    agency_factory: Callable[..., Agency], request_model: type[RunAgentInputType] = RunAgentInputCustom
):
    """
    Factory for a FastAPI endpoint handler that returns an AG-UI event stream for the given agency.

    Parameters:
        agency_factory: The agency factory to use for the endpoint.
        request_model: The request model to use for the endpoint. Defaults to RunAgentInputCustom.

    Returns:
        A FastAPI endpoint handler that returns an AG-UI event stream for the given agency.
    """

    async def handler(request: request_model, **kwargs):
        """Accepts AG-UI `RunAgentInput`, returns an AG-UI event stream."""

        if request.chat_history is not None:
            chat_history_dict = {}
            for key, value in request.chat_history.items():
                chat_history_dict[key] = json.loads(value.model_dump_json())

            def load_callback() -> dict:
                return chat_history_dict

        elif request.messages is not None:
            # Pull the default agent from the agency
            agency = agency_factory()
            default_agent = agency.entry_points[0]

            def load_callback() -> dict:
                return {
                    f"user->{default_agent.name}": {
                        "items": AguiAdapter.agui_messages_to_chat_history(request.messages),
                        "metadata": {},
                    }
                }
        else:

            def load_callback() -> dict:
                return {}

        # Choose / build an agent – here we just create a demo agent each time.
        agency = agency_factory(load_threads_callback=load_callback)

        event_generator, encoder = agui_event_generator(
            agency, request.thread_id, request.run_id, request.messages, **kwargs
        )

        return StreamingResponse(event_generator(), media_type=encoder.get_content_type())

    return handler


def make_agui_chat_endpoint(
    request_model: type[RunAgentInputType], agency_factory: Callable[..., Agency], verify_token
):
    """
    Legacy AG-UI chat endpoint handler with a required verify_token dependency.
    """
    generic_handler = make_fastapi_agui_chat_endpoint(agency_factory, request_model)

    async def handler(request: request_model, token: str = Depends(verify_token)):
        ret = await generic_handler(request)
        return ret

    return handler


def make_fastapi_metadata_endpoint(agency_metadata: dict):
    """
    Factory for a FastAPI endpoint handler that returns the metadata for the given agency.

    Parameters:
        agency_metadata: The metadata to return.

    Returns:
        A FastAPI endpoint handler that returns the metadata for the given agency.
    """

    async def handler():
        return {"metadata": agency_metadata}

    return handler


def make_metadata_endpoint(agency_metadata: dict, verify_token):
    """
    Legacy metadata endpoint handler with a required verify_token dependency.
    """
    generic_handler = make_fastapi_metadata_endpoint(agency_metadata)

    async def handler(token: str = Depends(verify_token)):
        ret = await generic_handler()
        return ret

    return handler


async def exception_handler(request, exc):
    """
    Exception handler for FastAPI endpoints. Returns a JSON response with the error message.
    """
    error_message = str(exc)
    if isinstance(exc, tuple):
        error_message = str(exc[1]) if len(exc) > 1 else str(exc[0])
    return JSONResponse(status_code=500, content={"error": error_message})
