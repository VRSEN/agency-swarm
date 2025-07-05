import asyncio
import json
from collections.abc import AsyncGenerator, Callable

from ag_ui.core import EventType, MessagesSnapshotEvent, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.encoder import EventEncoder
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agency_swarm.agency import Agency
from agency_swarm.ui.core.converters import AguiConverter, serialize


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
            chat_history_dict = {}
            for key, value in request.chat_history.items():
                chat_history_dict[key] = json.loads(value.model_dump_json())

            def load_callback() -> dict:
                return chat_history_dict

        else:

            def load_callback() -> dict:
                return {}

        agency_instance = agency_factory(load_threads_callback=load_callback)
        response = await agency_instance.get_response(
            message=request.message,
            recipient_agent=request.recipient_agent,
            additional_instructions=request.additional_instructions,
            file_ids=request.file_ids,
        )
        history = {
            thread_id: {"items": thread.items, "metadata": thread.metadata}
            for thread_id, thread in agency_instance.thread_manager._threads.items()
        }
        return {"response": response.final_output, "chat_history": history}

    return handler


# Streaming SSE endpoint
def make_stream_endpoint(request_model, agency_factory: Callable[..., Agency], verify_token):
    async def handler(request: request_model, token: str = Depends(verify_token)):
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

        async def event_generator():
            try:
                async for event in agency_instance.get_response_stream(
                    message=request.message,
                    recipient_agent=request.recipient_agent,
                    additional_instructions=request.additional_instructions,
                    file_ids=request.file_ids,
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


def make_agui_chat_endpoint(request_model, agency_factory: Callable[..., Agency], verify_token):
    async def handler(request: request_model, token: str = Depends(verify_token)):
        """Accepts AG-UI `RunAgentInput`, returns an AG-UI event stream."""

        encoder = EventEncoder()

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
                        "items": AguiConverter.agui_messages_to_chat_history(request.messages),
                        "metadata": {},
                    }
                }
        else:

            def load_callback() -> dict:
                return {}

        # Choose / build an agent – here we just create a demo agent each time.
        agency = agency_factory(load_threads_callback=load_callback)

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
                # Store in dict format to avoid converting to classes
                snapshot_messages = [message.model_dump() for message in request.messages]
                async for event in agency.get_response_stream(
                    message=request.messages[-1].content,
                ):
                    agui_event = AguiConverter.openai_to_agui_events(
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
        return {"metadata": agency_metadata}

    return handler


async def exception_handler(request, exc):
    error_message = str(exc)
    if isinstance(exc, tuple):
        error_message = str(exc[1]) if len(exc) > 1 else str(exc[0])
    return JSONResponse(status_code=500, content={"error": error_message})
