import asyncio
import inspect
import json
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Optional

import anyio
from anyio import (
    EndOfStream,
    create_memory_object_stream,
    fail_after,
)
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
_EXECUTOR: Optional[ThreadPoolExecutor] = None
_COMPLETION_LOCK = threading.Lock()  # Global lock for sequential completion processing

def get_executor() -> ThreadPoolExecutor:
    """Get the thread pool executor, ensuring it has been initialized."""
    global _EXECUTOR
    if _EXECUTOR is None:
        # Fallback initialization if not created by FastAPI lifecycle hooks
        print("WARNING: ThreadPoolExecutor not initialized by FastAPI lifecycle hooks. Creating now.")
        _EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
    return _EXECUTOR

def get_verify_token(app_token):
    auto_error = app_token is not None and app_token != ""
    security = HTTPBearer(auto_error=auto_error)
    def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
        if app_token is None or app_token == "":
            return None
        if not credentials or credentials.credentials != app_token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return credentials.credentials
    return verify_token

# Non‑streaming completion endpoint
def make_completion_endpoint(request_model, current_agency, verify_token):
    def handler(request: request_model, token: str = Depends(verify_token)):
        # Use lock to ensure sequential processing
        with _COMPLETION_LOCK:
            # Run completion sequentially instead of in a separate thread
            if request.threads:
                current_thread = get_threads(current_agency)
                if current_thread != request.threads:
                    override_threads(current_agency, request.threads)
            
            response = current_agency.get_completion(
                request.message,
                message_files=request.message_files,
                recipient_agent=request.recipient_agent,
                additional_instructions=request.additional_instructions,
                attachments=request.attachments,
                tool_choice=request.tool_choice,
                verbose=getattr(request, "verbose", False),
                response_format=request.response_format,
            )
            
            return {"response": response, "threads": get_threads(current_agency)}

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
                # Use lock to ensure sequential processing for streaming
                with _COMPLETION_LOCK:
                    if request.threads:
                        current_thread = get_threads(current_agency)
                        if current_thread != request.threads:
                            override_threads(current_agency, request.threads)
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

        worker: Future = get_executor().submit(run_completion)

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
            if inspect.iscoroutinefunction(tool_instance.run):
                result = await tool_instance.run()
            else:
                result = tool_instance.run()
            return {"response": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"Error": str(e)})
    return handler

async def exception_handler(request, exc):
    error_message = str(exc)
    if isinstance(exc, tuple):
        error_message = str(exc[1]) if len(exc) > 1 else str(exc[0])
    return JSONResponse(status_code=500, content={"error": error_message})

def override_threads(agency, threads: dict):
    try:
        _reset_agents_and_threads(agency)
        def load_threads(threads_dict: dict):
            return threads_dict
        def save_threads(threads_dict):
            pass
        if agency.threads_callbacks:
            agency.threads_callbacks['load'] = lambda: load_threads(threads)
        else:
            agency.threads_callbacks = {
                'load': lambda: load_threads(threads),
                'save': lambda threads: save_threads(threads)
            }
        agency._init_threads()
        agency._create_special_tools()
    except Exception as e:
        raise ValueError(f"Error overriding threads: {e}")
    
def get_threads(agency):
    loaded_thread_ids = {}
    for agent_name, threads in agency.agents_and_threads.items():
        if agent_name == "main_thread":
            continue
        loaded_thread_ids[agent_name] = {}
        for other_agent, thread in threads.items():
            loaded_thread_ids[agent_name][other_agent] = thread.id

    loaded_thread_ids["main_thread"] = agency.main_thread.id
    return loaded_thread_ids


def _reset_agents_and_threads(agency):
    """Helper function to return agents_and_threads to it's initial state (before init_threads)"""
    pre_loaded_dict = {}
    for sender_agent, recipients in agency.agents_and_threads.items():
        recipient_agents = {}
        if sender_agent == "main_thread" and not isinstance(recipients, dict):
            continue
        for recipient_agent in recipients.keys():
            recipient_agents[recipient_agent] = {
                "agent": sender_agent,
                "recipient_agent": recipient_agent
            }
        pre_loaded_dict[sender_agent] = recipient_agents
    agency.agents_and_threads = pre_loaded_dict
