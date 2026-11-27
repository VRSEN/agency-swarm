import atexit
import os
import shutil
import subprocess
from pathlib import Path

from agency_swarm import Agency
from agency_swarm.integrations.fastapi import run_fastapi


def _ensure_frontend_ready(fe_path: Path) -> str:
    """Return the npm executable path, installing frontend dependencies if missing."""
    npm_exe = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_exe is None:
        raise RuntimeError(
            "npm was not found on your PATH. Install Node.js (https://nodejs.org) "
            "and ensure `npm` is accessible before running CopilotDemoLauncher."
        )

    if not (fe_path / "node_modules").exists():
        print(
            "\033[93m[Copilot Demo] 'node_modules' not found in copilot app directory. "
            "Running 'npm install' to install frontend dependencies...\033[0m"
        )
        try:
            subprocess.check_call([npm_exe, "install", "--legacy-peer-deps"], cwd=fe_path)
            print(
                "\033[92m[Copilot Demo] Frontend dependencies installed successfully. "
                "Frontend might take a few seconds to load.\033[0m"
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to install frontend dependencies in {fe_path}. Please check your npm setup and try again."
            ) from e

    return npm_exe


def _format_url_host(host: str) -> str:
    """Return a client-connectable URL host segment for a bind address."""
    client_host = "localhost" if host in ("0.0.0.0", "::") else host
    if ":" in client_host and not client_host.startswith("["):
        return f"[{client_host}]"
    return client_host


class CopilotDemoLauncher:
    @staticmethod
    def start(
        agency_instance: Agency,
        host: str = "127.0.0.1",
        port: int = 8000,
        frontend_port: int = 3000,
        cors_origins: list[str] | None = None,
    ) -> None:
        """Launch the Copilot UI demo with backend and frontend servers."""
        fe_path = Path(__file__).parent / "copilot"
        npm_exe = _ensure_frontend_ready(fe_path)

        # When bound to all interfaces via explicit host="0.0.0.0" or "::", advertise
        # a client-connectable URL for the frontend. Also avoid a trailing slash:
        # FastAPI will 307-redirect, which can break SSE clients.
        url_host = _format_url_host(host)
        agency_name = getattr(agency_instance, "name", None) or "agency"
        os.environ["NEXT_PUBLIC_AG_UI_BACKEND_URL"] = f"http://{url_host}:{port}/{agency_name}/get_response_stream"

        proc = subprocess.Popen(
            [npm_exe, "run", "dev", "--", "-H", host, "-p", str(frontend_port)],
            cwd=fe_path,
        )
        atexit.register(proc.terminate)
        print(
            f"\n\033[92;1m🚀  Copilot UI running at http://{url_host}:{frontend_port}\n"
            "    It might take a moment for the page to load the first time you open it.\033[0m\n"
        )

        run_fastapi(
            agencies={agency_name: lambda **kwargs: agency_instance},
            host=host,
            port=port,
            app_token_env="",
            cors_origins=cors_origins,
            enable_agui=True,
        )
