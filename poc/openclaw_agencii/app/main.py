from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from agency_swarm.integrations.fastapi import run_fastapi
from app.agency import create_agency
from app.openclaw_proxy import OpenClawProxyConfig, create_openclaw_proxy_router
from app.openclaw_runtime import OpenClawRuntime, OpenClawRuntimeConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _resolve_logs_dir() -> str:
    requested = os.getenv("POC_LOGS_DIR", "/mnt/activity-logs")
    requested_path = Path(requested)
    try:
        requested_path.mkdir(parents=True, exist_ok=True)
        return str(requested_path)
    except OSError:
        fallback = Path("activity-logs").resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning("Falling back to local logs dir: %s", fallback)
        return str(fallback)


def _default_proxy_base_url() -> str:
    port = os.getenv("PORT", "8080")
    return f"http://127.0.0.1:{port}/openclaw/v1"


def create_app() -> FastAPI:
    runtime_config = OpenClawRuntimeConfig.from_env()
    runtime = OpenClawRuntime(runtime_config)

    app = run_fastapi(
        agencies={"openclaw-poc": create_agency},
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        app_token_env="APP_TOKEN",
        return_app=True,
        enable_agui=False,
        enable_logging=True,
        logs_dir=_resolve_logs_dir(),
    )
    if app is None:
        raise RuntimeError("FastAPI app initialization failed")

    proxy_config = OpenClawProxyConfig(
        upstream_base_url=runtime.upstream_base_url,
        upstream_token=runtime_config.gateway_token,
        timeout_seconds=float(os.getenv("OPENCLAW_PROXY_TIMEOUT_SECONDS", "120")),
    )
    app.include_router(create_openclaw_proxy_router(proxy_config), prefix="/openclaw", tags=["openclaw"])

    @app.on_event("startup")
    async def startup_runtime() -> None:
        if runtime_config.autostart:
            runtime.start()
        else:
            logger.info("OpenClaw runtime autostart disabled")

    @app.on_event("shutdown")
    async def shutdown_runtime() -> None:
        runtime.stop()

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {
            "ok": True,
            "openclaw": runtime.health(),
            "openclaw_proxy_base_url": os.getenv("OPENCLAW_PROXY_BASE_URL", _default_proxy_base_url()),
        }

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
