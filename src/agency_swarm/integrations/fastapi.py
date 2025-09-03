import logging
import os
from collections.abc import Callable, Mapping

from agents.tool import FunctionTool

from agency_swarm.agency import Agency
from agency_swarm.agent.core import Agent

logger = logging.getLogger(__name__)


def run_fastapi(
    agencies: Mapping[str, Callable[..., Agency]] | None = None,
    tools: list[type[FunctionTool]] | None = None,
    host: str = "0.0.0.0",
    port: int = 8000,
    app_token_env: str = "APP_TOKEN",
    return_app: bool = False,
    cors_origins: list[str] | None = None,
    enable_agui: bool = False,
    enable_logging: bool = False,
    logs_dir: str = "activity-logs",
):
    """Launch a FastAPI server exposing endpoints for multiple agencies and tools.

    Parameters
    ----------
    agencies : Mapping[str, Callable[..., Agency]] | None
        Mapping of endpoint name to a factory that returns an :class:`Agency`.
        The factory receives a ``load_threads_callback`` argument and is invoked
        on each request to provide a fresh agency instance with the
        conversation history preloaded.
    tools : list[type[FunctionTool]] | None
        Optional tools to expose under ``/tool`` routes.
    host, port, app_token_env, return_app, cors_origins :
        Standard FastAPI configuration options.
    enable_logging : bool
        Enable request tracking and file logging.
        When enabled, adds middleware to track requests and allows conditional
        file logging based on 'x-agency-log-id' header.
    logs_dir : str
        Directory to store log files when logging is enabled.
        Defaults to 'activity-logs'.
    """
    if (agencies is None or len(agencies) == 0) and (tools is None or len(tools) == 0):
        logger.warning("No endpoints to deploy. Please provide at least one agency or tool.")
        return

    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        from .fastapi_utils.endpoint_handlers import (
            exception_handler,
            get_verify_token,
            make_agui_chat_endpoint,
            make_logs_endpoint,
            make_metadata_endpoint,
            make_response_endpoint,
            make_stream_endpoint,
            make_tool_endpoint,
        )
        from .fastapi_utils.logging_middleware import (
            RequestTracker,
            setup_enhanced_logging,
        )
        from .fastapi_utils.request_models import BaseRequest, LogRequest, RunAgentInputCustom, add_agent_validator
    except ImportError as e:
        logger.error(f"FastAPI deployment dependencies are missing: {e}. Please install agency-swarm[fastapi] package")
        return

    app_token = os.getenv(app_token_env)
    if app_token is None or app_token == "":
        logger.warning("App token is not set. Authentication will be disabled.")
    verify_token = get_verify_token(app_token)

    app = FastAPI()

    # Setup logging if enabled
    if enable_logging:
        setup_enhanced_logging(logs_dir)
        app.add_middleware(RequestTracker)

    if cors_origins is None:
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    endpoints = []
    agency_names = []

    if agencies:
        for agency_name, agency_factory in agencies.items():
            if agency_name is None or agency_name == "":
                agency_name = "agency"
            agency_name = agency_name.replace(" ", "_")
            if agency_name in agency_names:
                raise ValueError(
                    f"Agency name {agency_name} is already in use. "
                    "Please provide a unique name in the agency's 'name' parameter."
                )
            agency_names.append(agency_name)

            # Store agent instances for easy lookup
            preview_instance = agency_factory(load_threads_callback=lambda: [])
            AGENT_INSTANCES: dict[str, Agent] = dict(preview_instance.agents.items())
            AgencyRequest = add_agent_validator(BaseRequest, AGENT_INSTANCES)
            agency_metadata = preview_instance.get_agency_structure()

            if enable_agui:
                app.add_api_route(
                    f"/{agency_name}/get_response_stream",
                    make_agui_chat_endpoint(RunAgentInputCustom, agency_factory, verify_token),
                    methods=["POST"],
                )
                endpoints.append(f"/{agency_name}/get_response_stream")
            else:
                app.add_api_route(
                    f"/{agency_name}/get_response",
                    make_response_endpoint(AgencyRequest, agency_factory, verify_token),
                    methods=["POST"],
                )
                app.add_api_route(
                    f"/{agency_name}/get_response_stream",
                    make_stream_endpoint(AgencyRequest, agency_factory, verify_token),
                    methods=["POST"],
                )
                endpoints.append(f"/{agency_name}/get_response")
                endpoints.append(f"/{agency_name}/get_response_stream")

            app.add_api_route(
                f"/{agency_name}/get_metadata",
                make_metadata_endpoint(agency_metadata, verify_token),
                methods=["GET"],
            )
            endpoints.append(f"/{agency_name}/get_metadata")

    if tools:
        for tool in tools:
            tool_name = tool.name if hasattr(tool, "name") else tool.__name__
            tool_handler = make_tool_endpoint(tool, verify_token)
            app.add_api_route(f"/tool/{tool_name}", tool_handler, methods=["POST"], name=tool_name)
            endpoints.append(f"/tool/{tool_name}")

    app.add_exception_handler(Exception, exception_handler)

    # Add get_logs endpoint if logging is enabled
    if enable_logging:
        app.add_api_route("/get_logs", make_logs_endpoint(LogRequest, logs_dir, verify_token), methods=["POST"])
        endpoints.append("/get_logs")

    logger.info("Created endpoints:\n" + "\n".join(endpoints))

    if return_app:
        return app

    logger.info(f"Starting FastAPI {'AG-UI ' if enable_agui else ''}server at http://{host}:{port}")

    uvicorn.run(app, host=host, port=port)
