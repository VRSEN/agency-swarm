from agency_swarm import Agency


class CopilotDemoLauncher:
    @staticmethod
    def start(
        agency_instance: Agency,
        host: str = "0.0.0.0",
        port: int = 8000,
        frontend_port: int = 3000,
        cors_origins: list[str] | None = None,
    ) -> None:
        """Launch the Copilot UI demo with backend and frontend servers."""
        import atexit
        import os
        import shutil
        import subprocess
        from pathlib import Path

        from agency_swarm.integrations.fastapi import run_fastapi

        fe_path = Path(__file__).parent / "copilot"

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
                subprocess.check_call([npm_exe, "install"], cwd=fe_path)
                print(
                    "\033[92m[Copilot Demo] Frontend dependencies installed successfully. "
                    "Frontend might take a few seconds to load.\033[0m"
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to install frontend dependencies in {fe_path}. Please check your npm setup and try again."
                ) from e

        os.environ["NEXT_PUBLIC_AG_UI_BACKEND_URL"] = (
            f"http://{host}:{port}/{getattr(agency_instance, 'name', None) or 'agency'}/get_response_stream/"
        )

        proc = subprocess.Popen(
            [npm_exe, "run", "dev", "--", "-p", str(frontend_port)],
            cwd=fe_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        atexit.register(proc.terminate)
        print(
            f"\n\033[92;1m🚀  Copilot UI running at http://localhost:{frontend_port}\n"
            "    It might take a moment for the page to load the first time you open it.\033[0m\n"
        )

        run_fastapi(
            agencies={getattr(agency_instance, "name", None) or "agency": lambda **kwargs: agency_instance},
            host=host,
            port=port,
            app_token_env="",
            cors_origins=cors_origins,
            enable_agui=True,
        )
