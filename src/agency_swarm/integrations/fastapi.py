import asyncio
import logging
import os
from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import Any

from agents.tool import FunctionTool

from agency_swarm.agency import Agency
from agency_swarm.agent.core import Agent
from agency_swarm.integrations.realtime import (
    RealtimeSessionFactory,
    _forward_session_events as _rt_forward_session_events,
    _handle_client_payload as _rt_handle_client_payload,
    build_model_settings,
)

logger = logging.getLogger(__name__)


def run_fastapi(
    agencies: Mapping[str, Callable[..., Agency]] | None = None,
    tools: list[type[FunctionTool]] | None = None,
    host: str = "0.0.0.0",
    port: int = 8000,
    server_url: str | None = None,
    app_token_env: str = "APP_TOKEN",
    return_app: bool = False,
    cors_origins: list[str] | None = None,
    enable_agui: bool = False,
    enable_logging: bool = False,
    logs_dir: str = "activity-logs",
    enable_realtime: bool = False,
    realtime_options: dict[str, Any] | None = None,
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
    server_url : str | None
        Optional base URL to be included in the server OpenAPI schema.
        Defaults to ``http://{host}:{port}``
    enable_logging : bool
        Enable request tracking and file logging.
        When enabled, adds middleware to track requests and allows conditional
        file logging based on 'x-agency-log-id' header.
    logs_dir : str
        Directory to store log files when logging is enabled.
        Defaults to 'activity-logs'.
    enable_realtime : bool
        When True, registers a websocket endpoint for each agency that mirrors the realtime
        helper. Requires FastAPI extras.
    realtime_options : dict[str, Any] | None
        Optional configuration applied to realtime endpoints (e.g. ``model``, ``voice``,
        ``turn_detection``). Matches the keyword arguments of :func:`run_realtime`.
    """
    if (agencies is None or len(agencies) == 0) and (tools is None or len(tools) == 0):
        logger.warning("No endpoints to deploy. Please provide at least one agency or tool.")
        return

    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.websockets import WebSocket as StarletteWebSocket, WebSocketDisconnect

        from .fastapi_utils.endpoint_handlers import (
            ActiveRunRegistry,
            exception_handler,
            get_verify_token,
            make_agui_chat_endpoint,
            make_cancel_endpoint,
            make_logs_endpoint,
            make_metadata_endpoint,
            make_response_endpoint,
            make_stream_endpoint,
        )
        from .fastapi_utils.logging_middleware import (
            RequestTracker,
            setup_enhanced_logging,
        )
        from .fastapi_utils.request_models import (
            BaseRequest,
            CancelRequest,
            LogRequest,
            RunAgentInputCustom,
            add_agent_validator,
        )
        from .fastapi_utils.tool_endpoints import make_tool_endpoint
    except ImportError as e:
        logger.error(f"FastAPI deployment dependencies are missing: {e}. Please install agency-swarm[fastapi] package")
        return

    dry_run_env = os.getenv("DRY_RUN", "")
    DRY_RUN = str(dry_run_env).strip().lower() in {"1", "true", "yes", "on"}

    app_token = os.getenv(app_token_env)
    if app_token is None or app_token == "":
        logger.warning("App token is not set. Authentication will be disabled.")
    verify_token = get_verify_token(app_token)

    if server_url:
        base_url = server_url
    elif host == "0.0.0.0":
        base_url = f"http://localhost:{port}"
    else:
        base_url = f"http://{host}:{port}"

    app = FastAPI(servers=[{"url": base_url}])

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
            if DRY_RUN:
                # In DRY_RUN, avoid building validators;
                agency_metadata = preview_instance.get_agency_structure()
            else:
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
                    run_registry = ActiveRunRegistry()
                    app.add_api_route(
                        f"/{agency_name}/get_response",
                        make_response_endpoint(AgencyRequest, agency_factory, verify_token),
                        methods=["POST"],
                    )
                    app.add_api_route(
                        f"/{agency_name}/get_response_stream",
                        make_stream_endpoint(
                            AgencyRequest,
                            agency_factory,
                            verify_token,
                            run_registry,
                        ),
                        methods=["POST"],
                    )
                    app.add_api_route(
                        f"/{agency_name}/cancel_response_stream",
                        make_cancel_endpoint(CancelRequest, verify_token, run_registry),
                        methods=["POST"],
                    )
                    endpoints.append(f"/{agency_name}/get_response")
                    endpoints.append(f"/{agency_name}/get_response_stream")
                    endpoints.append(f"/{agency_name}/cancel_response_stream")

                if enable_realtime:
                    realtime_defaults = dict(realtime_options or {})
                    route_path = f"/{agency_name}/realtime"

                    @app.websocket(route_path)
                    async def realtime_websocket(
                        websocket: StarletteWebSocket,
                        _agency_factory: Callable[..., Agency] = agency_factory,
                        _agency_name: str = agency_name,
                        _realtime_defaults: dict[str, Any] = realtime_defaults,
                        _app_token: str | None = app_token,
                    ) -> None:
                        auth_header = websocket.headers.get("authorization")
                        if _app_token:
                            if not auth_header or not auth_header.lower().startswith("bearer "):
                                await websocket.close(code=1008, reason="Unauthorized")
                                return
                            provided_token = auth_header.split(" ", 1)[1].strip()
                            if provided_token != _app_token:
                                await websocket.close(code=1008, reason="Unauthorized")
                                return

                        await websocket.accept()
                        logger.info("Realtime websocket accepted for %s from %s", _agency_name, websocket.client)
                        session = None
                        try:
                            try:
                                agency_instance = _agency_factory(load_threads_callback=lambda: [])
                            except Exception:
                                logger.exception("Failed to instantiate agency for realtime endpoint", exc_info=True)
                                await websocket.close(code=1011, reason="Failed to initialize agency.")
                                return

                            realtime_agency = agency_instance.to_realtime()
                            entry_voice = getattr(realtime_agency.entry_agent, "voice", None)
                            config = dict(_realtime_defaults)
                            base_settings = build_model_settings(
                                model=config.get("model", "gpt-realtime"),
                                voice=config.get("voice", entry_voice),
                                input_audio_format=config.get("input_audio_format"),
                                output_audio_format=config.get("output_audio_format"),
                                turn_detection=config.get("turn_detection"),
                                input_audio_noise_reduction=config.get("input_audio_noise_reduction"),
                            )
                            session_factory = RealtimeSessionFactory(realtime_agency, base_settings)
                        except Exception:
                            logger.exception("Failed to prepare realtime session factory", exc_info=True)
                            await websocket.close(code=1011, reason="Failed to initialize realtime session.")
                            return

                        try:
                            session = await session_factory.create_session()
                        except Exception:
                            logger.exception("Failed to initialize realtime session", exc_info=True)
                            await websocket.close(code=1011, reason="Failed to initialize realtime session.")
                            return

                        try:
                            async with session as realtime_session:
                                events_task = asyncio.create_task(
                                    _rt_forward_session_events(
                                        realtime_session,
                                        websocket.send_text,
                                        initial_voice=session_factory.default_voice,
                                    )
                                )
                                try:
                                    while True:
                                        message = await websocket.receive()
                                        message_type = message.get("type")
                                        if message_type == "websocket.disconnect":
                                            break
                                        if message_type != "websocket.receive":
                                            continue

                                        text_data = message.get("text")
                                        if text_data is not None:
                                            await _rt_handle_client_payload(realtime_session, text_data)
                                            continue

                                        bytes_data = message.get("bytes")
                                        if bytes_data is not None:
                                            await realtime_session.send_audio(bytes_data)
                                except WebSocketDisconnect:
                                    logger.info(
                                        "Realtime websocket disconnected by client %s for %s",
                                        websocket.client,
                                        _agency_name,
                                    )
                                except Exception:
                                    logger.exception(
                                        "Error while handling realtime websocket traffic for %s",
                                        _agency_name,
                                        exc_info=True,
                                    )
                                    await websocket.close(code=1011, reason="Realtime session error.")
                                finally:
                                    events_task.cancel()
                                    with suppress(asyncio.CancelledError):
                                        await events_task
                        finally:
                            if session is not None:
                                with suppress(Exception):
                                    await session.close()

                    endpoints.append(route_path)

            app.add_api_route(
                f"/{agency_name}/get_metadata",
                make_metadata_endpoint(agency_metadata, verify_token),
                methods=["GET"],
            )
            endpoints.append(f"/{agency_name}/get_metadata")

    if tools and not DRY_RUN:
        for tool in tools:
            tool_name = tool.name if hasattr(tool, "name") else tool.__name__
            tool_handler = make_tool_endpoint(tool, verify_token)
            app.add_api_route(
                f"/tool/{tool_name}",
                tool_handler,
                methods=["POST"],
                name=tool_name,
                operation_id=tool_name,
            )
            endpoints.append(f"/tool/{tool_name}")

        logger.info(f"📋 Tool schemas available at: {base_url}/openapi.json")
        logger.info(f"   Or use: ToolFactory.get_openapi_schema(tools, '{base_url}') for programmatic access")

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
