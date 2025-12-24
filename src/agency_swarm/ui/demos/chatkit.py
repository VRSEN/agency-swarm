from agency_swarm import Agency


class ChatkitDemoLauncher:
    @staticmethod
    def start(
        agency_instance: Agency,
        host: str = "0.0.0.0",
        port: int = 8000,
        frontend_port: int = 3000,
        cors_origins: list[str] | None = None,
        open_browser: bool = True,
    ) -> None:
        """Launch the ChatKit UI demo with backend and frontend servers."""
        import atexit
        import os
        import shutil
        import subprocess
        import threading
        import time
        import webbrowser
        from pathlib import Path

        from agency_swarm.integrations.fastapi import run_fastapi

        fe_path = Path(__file__).parent / "chatkit"

        npm_exe = shutil.which("npm") or shutil.which("npm.cmd")
        if npm_exe is None:
            raise RuntimeError(
                "npm was not found on your PATH. Install Node.js (https://nodejs.org) "
                "and ensure `npm` is accessible before running ChatkitDemoLauncher."
            )

        if not (fe_path / "node_modules").exists():
            print(
                "\033[93m[ChatKit Demo] 'node_modules' not found in chatkit app directory. "
                "Running 'npm install' to install frontend dependencies...\033[0m"
            )
            try:
                subprocess.check_call([npm_exe, "install"], cwd=fe_path)
                print(
                    "\033[92m[ChatKit Demo] Frontend dependencies installed successfully. "
                    "Frontend might take a few seconds to load.\033[0m"
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to install frontend dependencies in {fe_path}. Please check your npm setup and try again."
                ) from e

        agency_name = getattr(agency_instance, "name", None) or "agency"
        agency_name = agency_name.replace(" ", "_")

        # Set environment variables for the Vite frontend
        os.environ["CHATKIT_BACKEND_URL"] = f"http://{host}:{port}"
        os.environ["CHATKIT_FRONTEND_PORT"] = str(frontend_port)
        os.environ["CHATKIT_AGENCY_NAME"] = agency_name

        proc = subprocess.Popen(
            [npm_exe, "run", "dev"],
            cwd=fe_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        atexit.register(proc.terminate)

        url = f"http://localhost:{frontend_port}"
        print(
            f"\n\033[92;1m🚀  ChatKit UI running at {url}\n"
            "    It might take a moment for the page to load the first time you open it.\033[0m\n"
        )

        if open_browser:

            def delayed_open() -> None:
                time.sleep(3)
                webbrowser.open(url)

            threading.Thread(target=delayed_open, daemon=True).start()

        run_fastapi(
            agencies={agency_name: lambda **kwargs: agency_instance},
            host=host,
            port=port,
            app_token_env="",
            cors_origins=cors_origins,
            enable_chatkit=True,
        )
