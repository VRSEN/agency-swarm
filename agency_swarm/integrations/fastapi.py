import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Type

from dotenv import load_dotenv

from agency_swarm.agency import Agency
from agency_swarm.agents import Agent
from agency_swarm.tools import BaseTool

load_dotenv()


def run_fastapi(
    agencies: Optional[List[Agency]] = None,
    tools: Optional[List[Type[BaseTool]]] = None,
    host: str = "0.0.0.0",
    port: int = 8000,
    app_token_env: str = "APP_TOKEN",
    return_app: bool = False,
):
    """
    Launch a FastAPI server exposing endpoints for multiple agencies and tools.
    Each agency is deployed at /[agency-name]/get_completion and /[agency-name]/get_completion_stream.
    Each tool is deployed at /tool/[tool-name].
    """
    if (agencies is None or len(agencies) == 0) and (tools is None or len(tools) == 0):
        print("No endpoints to deploy. Please provide at least one agency or tool.")
        return

    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        from .fastapi_utils.endpoint_handlers import (
            exception_handler,
            get_verify_token,
            make_completion_endpoint,
            make_stream_endpoint,
            make_tool_endpoint,
        )
        from .fastapi_utils.request_models import BaseRequest, add_agent_validator
    except ImportError:
        print(
            "FastAPI deployment dependencies are missing. Please install agency-swarm[fastapi] package"
        )
        return

    app_token = os.getenv(app_token_env)
    if app_token is None or app_token == "":
        print(f"Warning: {app_token_env} is not set. Authentication will be disabled.")
    verify_token = get_verify_token(app_token)

    @asynccontextmanager
    async def lifespan(app):
        # Startup logic
        global _EXECUTOR
        from .fastapi_utils.endpoint_handlers import _EXECUTOR, _MAX_WORKERS
        if _EXECUTOR is None:
            print("Initializing ThreadPoolExecutor in FastAPI startup event")
            _EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
        else:
            print("ThreadPoolExecutor already initialized")
        try:
            yield
        finally:
            # Shutdown logic
            if _EXECUTOR is not None:
                print("Shutting down ThreadPoolExecutor in FastAPI shutdown event")
                _EXECUTOR.shutdown(wait=False, cancel_futures=True)
                _EXECUTOR = None
            else:
                print("No ThreadPoolExecutor to shut down")

    app = FastAPI(lifespan=lifespan)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    endpoints = []
    agency_names = []

    if agencies:
        for idx, agency in enumerate(agencies):
            agency_name = getattr(agency, "name", None)
            if agency_name is None:
                agency_name = "agency" if len(agencies) == 1 else f"agency_{idx+1}"
            agency_name = agency_name.replace(" ", "_")
            if agency_name in agency_names:
                raise ValueError(
                    f"Agency name {agency_name} is already in use. "
                    "Please provide a unique name in the agency's 'name' parameter."
                )
            agency_names.append(agency_name)

            # Store agent instances for easy lookup
            AGENT_INSTANCES: Dict[str, "Agent"] = {
                agent.name: agent for agent in agency.agents
            }

            class VerboseRequest(BaseRequest):
                verbose: bool = False

            AgencyRequest = add_agent_validator(VerboseRequest, AGENT_INSTANCES)
            AgencyRequestStreaming = add_agent_validator(BaseRequest, AGENT_INSTANCES)

            app.add_api_route(
                f"/{agency_name}/get_completion",
                make_completion_endpoint(AgencyRequest, agency, verify_token),
                methods=["POST"],
            )
            app.add_api_route(
                f"/{agency_name}/get_completion_stream",
                make_stream_endpoint(AgencyRequestStreaming, agency, verify_token),
                methods=["POST"],
            )
            endpoints.append(f"/{agency_name}/get_completion")
            endpoints.append(f"/{agency_name}/get_completion_stream")

    if tools:
        for tool in tools:
            tool_name = tool.__name__
            tool_handler = make_tool_endpoint(tool, verify_token)
            app.add_api_route(
                f"/tool/{tool_name}", tool_handler, methods=["POST"], name=tool_name
            )
            endpoints.append(f"/tool/{tool_name}")

    app.add_exception_handler(Exception, exception_handler)

    print("Created endpoints:\n" + "\n".join(endpoints))

    if return_app:
        return app

    print(f"Starting FastAPI server at http://{host}:{port}")
    
    uvicorn.run(app, host=host, port=port)
