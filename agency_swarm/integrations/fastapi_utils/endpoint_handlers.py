import json
import threading
from queue import Queue
from typing import override

import anyio
from openai.types.beta import AssistantStreamEvent
from fastapi import Depends, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from agency_swarm.util.streaming import AgencyEventHandler


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

def make_completion_endpoint(request_model, current_agency, verify_token):
    async def handler(
        request: request_model,
        token: str = Depends(verify_token),
    ):
        def run_sync():
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
        # Run in a thread to avoid event loop conflicts with mcp servers
        response = await anyio.to_thread.run_sync(run_sync)
        return {"response": response}

    return handler

def make_stream_endpoint(request_model, current_agency, verify_token):
    async def handler(
        request: request_model,
        token: str = Depends(verify_token),
    ):
        queue = Queue()

        class StreamEventHandler(AgencyEventHandler):
            @override
            def on_event(self, event: AssistantStreamEvent) -> None:
                queue.put(event.model_dump())

            @classmethod
            def on_all_streams_end(cls):
                queue.put("[DONE]")

            @classmethod
            def on_exception(cls, exception: Exception):
                # Store the actual exception
                queue.put({"error": str(exception)})

        async def generate_response():
            try:
                def run_completion():
                    try:
                        current_agency.get_completion_stream(
                            request.message,
                            message_files=request.message_files,
                            recipient_agent=request.recipient_agent,
                            additional_instructions=request.additional_instructions,
                            attachments=request.attachments,
                            tool_choice=request.tool_choice,
                            response_format=request.response_format,
                            event_handler=StreamEventHandler
                        )
                    except Exception as e:
                        # Send the actual exception
                        queue.put({"error": str(e)})

                thread = threading.Thread(target=run_completion)
                thread.start()

                while True:
                    try:
                        event = queue.get(timeout=30)
                        if event == "[DONE]":
                            break
                        # If it's an error event
                        if isinstance(event, dict) and "error" in event:
                            yield f"data: {json.dumps(event)}\n\n"
                            break
                        yield f"data: {json.dumps(event)}\n\n"
                    except Queue.Empty:
                        yield f"data: {json.dumps({'error': 'Request timed out'})}\n\n"
                        break
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        break

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    return handler

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

