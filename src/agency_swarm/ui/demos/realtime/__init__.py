from pathlib import Path
from typing import Any

from agency_swarm.agency.core import Agency


class RealtimeDemoLauncher:
    """Launch the realtime browser demo using a provided Agency Swarm agent graph."""

    @staticmethod
    def start(
        agency: Agency,
        *,
        host: str = "0.0.0.0",
        port: int = 8000,
        model: str = "gpt-realtime",
        voice: str | None = "alloy",
        turn_detection: dict[str, Any] | None = None,
        input_audio_format: str | None = None,
        output_audio_format: str | None = None,
        input_audio_noise_reduction: dict[str, Any] | None = None,
        cors_origins: list[str] | None = None,
    ) -> None:
        """Start the realtime demo server and keep it running until interrupted."""
        if not isinstance(agency, Agency):
            raise TypeError("RealtimeDemoLauncher.start expects an Agency instance.")
        if not agency.entry_points:
            raise ValueError("RealtimeDemoLauncher.start requires the Agency to define at least one entry point.")
        entry_agent = agency.entry_points[0]

        try:
            import uvicorn
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                'Realtime demo requires uvicorn. Install extras: pip install "agency-swarm[fastapi]"'
            ) from exc

        try:
            from agency_swarm.integrations.realtime import (
                RealtimeSessionFactory,
                build_model_settings,
            )
            from agency_swarm.ui.demos.realtime.app.server import create_realtime_demo_app
        except ImportError as exc:  # pragma: no cover - import guard
            missing = getattr(exc, "name", "") or str(exc)
            if "fastapi" in missing or "starlette" in missing:
                raise RuntimeError(
                    'Realtime demo requires FastAPI. Install extras: pip install "agency-swarm[fastapi]"'
                ) from exc
            raise RuntimeError("Realtime demo assets are missing from the installation.") from exc

        demo_static_dir = Path(__file__).parent / "app" / "static"
        if not demo_static_dir.exists():
            raise RuntimeError(f"Realtime demo static assets not found at {demo_static_dir}.")

        base_settings = build_model_settings(
            model=model,
            voice=voice,
            input_audio_format=input_audio_format,
            output_audio_format=output_audio_format,
            turn_detection=turn_detection,
            input_audio_noise_reduction=input_audio_noise_reduction,
        )
        realtime_agency = agency.to_realtime(entry_agent)
        session_factory = RealtimeSessionFactory(realtime_agency, base_settings)
        app = create_realtime_demo_app(
            session_factory,
            static_dir=demo_static_dir,
            cors_origins=cors_origins,
        )

        display_host = host if host != "0.0.0.0" else "localhost"
        print(
            f"\n\033[92;1mRealtime demo running\033[0m\nFrontend: http://{display_host}:{port}\nPress Ctrl+C to stop.\n"
        )

        uvicorn.run(
            app,
            host=host,
            port=port,
            ws_max_size=16 * 1024 * 1024,
        )


__all__ = ["RealtimeDemoLauncher"]
