import os
import json
from typing import Any
from concurrent.futures import ThreadPoolExecutor, Future

import anyio
from anyio import (
    EndOfStream,
    create_memory_object_stream,
    fail_after,
)
import asyncio
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai.types.beta import AssistantStreamEvent

from agency_swarm.util.streaming import AgencyEventHandler

try:
    from typing import override  # py >= 3.12
except ImportError:  # pragma: no cover – fallback path
    from typing_extensions import override  # type: ignore

_n_cpus = os.cpu_count() or 1
_MAX_WORKERS = max(1, int(os.getenv("STREAM_THREAD_POOL_SIZE", _n_cpus * 4)))
_EXECUTOR: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)

def get_verify_token(app_token):
    auto_error = app_token is not None and app_token != ""
    security = HTTPBearer(auto_error=auto_error)
    async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
        if app_token is None or app_token == "":
            return None
        if not credentials or credentials.credentials != app_token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return credentials.credentials
    return verify_token

# Non‑streaming completion endpoint
def make_completion_endpoint(request_model, current_agency, verify_token):
    async def handler(request: request_model, token: str = Depends(verify_token)):
        def call_completion() -> Any:
            return current_agency.get_completion(
                request.message,
                message_files=request.message_files,
                recipient_agent=request.recipient_agent,
                additional_instructions=request.additional_instructions,
                attachments=request.attachments,
                tool_choice=request.tool_choice,
                verbose=getattr(request, "verbose", False),
                response_format=request.response_format,
            )

        response = await anyio.to_thread.run_sync(call_completion, cancellable=True)
        return {"response": response}

    return handler

# Streaming SSE endpoint
def make_stream_endpoint(request_model, current_agency, verify_token):
    """FastAPI SSE endpoint factory using AnyIO (handles back‑pressure)."""

    async def handler(request: request_model, token: str = Depends(verify_token)):
        # Async queue bridging producer thread → event‑loop
        send_ch, recv_ch = create_memory_object_stream(256)

        loop = asyncio.get_running_loop()  # capture once

        def _threadsafe_send(item):
            """Block the calling thread until the item is accepted."""
            try:
                asyncio.run_coroutine_threadsafe(send_ch.send(item), loop).result()
            except RuntimeError:
                # Event‑loop is closed (shutdown). Drop the message.
                pass

        class StreamEventHandler(AgencyEventHandler):
            @override
            def on_event(self, event: AssistantStreamEvent) -> None:
                _threadsafe_send(event.model_dump())

            @classmethod
            def on_all_streams_end(cls):
                _threadsafe_send("[DONE]")

            @classmethod
            def on_exception(cls, exc: Exception):
                _threadsafe_send({"error": str(exc)})

        def run_completion() -> None:
            try:
                current_agency.get_completion_stream(
                    request.message,
                    message_files=request.message_files,
                    recipient_agent=request.recipient_agent,
                    additional_instructions=request.additional_instructions,
                    attachments=request.attachments,
                    tool_choice=request.tool_choice,
                    response_format=request.response_format,
                    event_handler=StreamEventHandler,
                )
            except Exception as exc:
                _threadsafe_send({"error": str(exc)})
                raise

        worker: Future = _EXECUTOR.submit(run_completion)

        # ---------- Async generator consumed by StreamingResponse ----------
        async def generate_response():
            try:
                while True:
                    try:
                        with fail_after(30):
                            event = await recv_ch.receive()
                    except TimeoutError:
                        yield "data: " + json.dumps({"error": "Request timed out"}) + "\n\n"
                        break
                    except EndOfStream:
                        break

                    if event == "[DONE]":
                        break
                    if isinstance(event, dict) and "error" in event:
                        yield "data: " + json.dumps(event) + "\n\n"
                        break

                    yield "data: " + json.dumps(event) + "\n\n"
            except anyio.get_cancelled_exc_class():
                worker.cancel()  # cannot forcibly kill, but we stop reading
                raise
            finally:
                send_ch.close()  # unblock producer if still running

        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return handler

# Tool endpoint
def make_tool_endpoint(tool, verify_token):
    async def handler(request: Request, token: str = Depends(verify_token)):
        try:
            data = await request.json()
            tool_instance = tool(**data) if isinstance(tool, type) else tool
            return {"response": tool_instance.run()}
        except Exception as e:
            return JSONResponse(status_code=500, content={"Error": str(e)})
    return handler

async def exception_handler(request, exc):
    error_message = str(exc)
    if isinstance(exc, tuple):
        error_message = str(exc[1]) if len(exc) > 1 else str(exc[0])
    return JSONResponse(status_code=500, content={"error": error_message})

