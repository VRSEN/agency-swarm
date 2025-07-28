import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, ParamSpec

from agents.tool import FunctionTool
from dotenv import load_dotenv

from agency_swarm.agency import Agency
from agency_swarm.agent import Agent

P = ParamSpec("P")
logger = logging.getLogger(__name__)

try:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware import _MiddlewareFactory

    from .fastapi_utils.endpoint_handlers import (
        exception_handler,
        get_verify_token,
        make_agui_chat_endpoint,
        make_metadata_endpoint,
        make_response_endpoint,
        make_stream_endpoint,
        make_tool_endpoint,
    )
    from .fastapi_utils.request_models import BaseRequest, RunAgentInputCustom, add_agent_validator
except ImportError:
    logger.error("FastAPI deployment dependencies are missing. Please install agency-swarm[fastapi] package")

load_dotenv()


class AgencySwarmFastAPIHelper:
    agencies: Mapping[str, Callable[..., Agency]] = {}
    app: FastAPI | None = None
    agency_names: list[str] = []
    tools: list[type[FunctionTool]] = []
    route_prefix: str = "/"

    def __init__(self, app: FastAPI | None = None, route_prefix: str = "", **kwargs):
        self.app = app
        if self.app is None:
            self.app = FastAPI()

        self.route_prefix = route_prefix or "/"
        if not self.route_prefix.endswith("/"):
            self.route_prefix += "/"
        if not self.route_prefix.startswith("/"):
            self.route_prefix = "/" + self.route_prefix

    def add_middleware(self, middleware_class: _MiddlewareFactory[P], *args: P.args, **kwargs: P.kwargs) -> None:
        self.app.add_middleware(middleware_class, *args, **kwargs)

    def add_api_route(self, path: str, endpoint: Callable[..., Any], *args, **kwargs):
        self.app.add_api_route(path, endpoint, *args, **kwargs)

    def add_exception_handler(self, exception_handler: Callable[..., Any]):
        self.app.add_exception_handler(Exception, exception_handler)

    def add_agency(
        self,
        agency_name: str,
        agency_factory: Callable[..., Agency],
        handlers: Mapping[str, tuple[str, Callable[..., Any]]],
    ) -> list[str]:
        """
        Add an agency to the FastAPI app.

        Parameters:
            agency_name: The name of the agency.
            agency_factory: The factory that returns an :class:`Agency`.
            handlers: A mapping of handler routes to their method (GET or POST) and handler function.

        Returns:
        """
        if agency_name in self.agencies:
            raise ValueError(
                f"Agency name {agency_name} is already in use. "
                "Please provide a unique name in the agency's 'name' parameter."
            )
        self.agencies[agency_name] = agency_factory
        self.agency_names.append(agency_name)

        endpoints_added = []

        for handler_route, (method, handler) in handlers.items():
            self.add_api_route(
                f"{self.route_prefix}{agency_name}/{handler_route}",
                handler,
                methods=[method],
            )
            endpoints_added.append(f"{self.route_prefix}{agency_name}/{handler_route}")

        return endpoints_added

    def add_tool(
        self,
        tool: type[FunctionTool],
        handler: Callable[..., Any],
    ) -> str:
        self.tools.append(tool)
        self.add_api_route(f"{self.route_prefix}tool/{tool.name}", handler, methods=["POST"], name=tool.name)
        return f"{self.route_prefix}tool/{tool.name}"


def run_fastapi(
    agencies: Mapping[str, Callable[..., Agency]] | None = None,
    tools: list[type[FunctionTool]] | None = None,
    host: str = "0.0.0.0",
    port: int = 8000,
    app_token_env: str = "APP_TOKEN",
    return_app: bool = False,
    cors_origins: list[str] | None = None,
    enable_agui: bool = False,
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
    """
    if (agencies is None or len(agencies) == 0) and (tools is None or len(tools) == 0):
        logger.warning("No endpoints to deploy. Please provide at least one agency or tool.")
        return

    app_token = os.getenv(app_token_env)
    if app_token is None or app_token == "":
        logger.warning("App token is not set. Authentication will be disabled.")
    verify_token = get_verify_token(app_token)

    helper = AgencySwarmFastAPIHelper()

    if cors_origins is None:
        cors_origins = ["*"]

    helper.add_middleware(
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
            preview_instance = agency_factory(load_threads_callback=lambda: {})
            AGENT_INSTANCES: dict[str, Agent] = dict(preview_instance.agents.items())
            AgencyRequest = add_agent_validator(BaseRequest, AGENT_INSTANCES)
            agency_metadata = preview_instance.get_agency_structure()

            handlers = {}
            if enable_agui:
                handlers["get_response_stream"] = (
                    "POST",
                    make_agui_chat_endpoint(RunAgentInputCustom, agency_factory, verify_token),
                )
            else:
                handlers["get_response"] = ("POST", make_response_endpoint(AgencyRequest, agency_factory, verify_token))
                handlers["get_response_stream"] = (
                    "POST",
                    make_stream_endpoint(AgencyRequest, agency_factory, verify_token),
                )
            handlers["get_metadata"] = ("GET", make_metadata_endpoint(agency_metadata, verify_token))

            endpoints_added = helper.add_agency(agency_name, agency_factory, handlers)
            endpoints.extend(endpoints_added)

    if tools:
        for tool in tools:
            tool_handler = make_tool_endpoint(tool, verify_token)
            endpoint = helper.add_tool(tool, tool_handler)
            endpoints.append(endpoint)

    helper.add_exception_handler(Exception, exception_handler)

    logger.info("Created endpoints:\n" + "\n".join(endpoints))

    if return_app:
        return helper.app

    logger.info(f"Starting FastAPI {'AG-UI ' if enable_agui else ''}server at http://{host}:{port}")

    uvicorn.run(helper.app, host=host, port=port)
