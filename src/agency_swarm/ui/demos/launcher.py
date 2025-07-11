class CopilotDemoLauncher:
    def start(
        agency_instance,
        host: str = "0.0.0.0",
        port: int = 8000,
        frontend_port: int = 3000,
        cors_origins: list[str] | None = None,
    ):
        """Launch the Copilot UI demo with backend and frontend servers."""
        import atexit
        import os
        import shutil
        import subprocess
        from pathlib import Path

        from agency_swarm.integrations.fastapi import run_fastapi

        fe_path = Path(__file__).parent / "copilot"

        # Safety checks – ensure Node.js environment is ready
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

        # Before starting the frontend process
        os.environ["NEXT_PUBLIC_AG_UI_BACKEND_URL"] = (
            f"http://{host}:{port}/{getattr(agency_instance, 'name', None) or 'agency'}/get_response_stream/"
        )

        # Start the frontend
        proc = subprocess.Popen(
            [npm_exe, "run", "dev", "--", "-p", str(frontend_port)],
            cwd=fe_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        # Ensure we clean up on ^C / exit
        atexit.register(proc.terminate)
        print(
            f"\n\033[92;1m🚀  Copilot UI running at http://localhost:{frontend_port}\n"
            "    It might take a moment for the page to load the first time you open it.\033[0m\n"
        )

        # Start the backend
        run_fastapi(
            agencies={getattr(agency_instance, "name", None) or "agency": lambda **kwargs: agency_instance},
            host=host,
            port=port,
            app_token_env="",
            cors_origins=cors_origins,
            enable_agui=True,
        )


class TerminalDemoLauncher:
    def start(agency_instance):
        """
        Executes agency in the terminal with autocomplete for recipient agent names.
        """
        import asyncio
        import logging
        import uuid

        from ..core.converters import ConsoleEventConverter

        logger = logging.getLogger(__name__)

        recipient_agents = [str(agent.name) for agent in agency_instance.entry_points]

        chat_id = f"run_demo_chat_{uuid.uuid4()}"

        event_converter = ConsoleEventConverter()

        async def main_loop():
            while True:
                event_converter.console.rule()
                message = input("👤 USER: ")

                if not message:
                    continue

                recipient_agent = None
                if "@" in message:
                    recipient_agent_name = message.split("@")[1].split(" ")[0]
                    message = message.replace(f"@{recipient_agent_name}", "").strip()
                    try:
                        recipient_agent = [
                            agent for agent in recipient_agents if agent.lower() == recipient_agent_name.lower()
                        ][0]
                    except Exception:
                        logger.error(f"Recipient agent {recipient_agent_name} not found.")
                        continue

                # Default to first entry point if not specified
                if recipient_agent is None and agency_instance.entry_points:
                    recipient_agent = agency_instance.entry_points[0].name

                try:
                    async for event in agency_instance.get_response_stream(
                        message=message,
                        recipient_agent=recipient_agent,
                        chat_id=chat_id,
                    ):
                        event_converter.openai_to_message_output(event, recipient_agent)
                    print()  # Newline after stream
                except Exception as e:
                    logger.error(f"Error during streaming: {e}", exc_info=True)

        asyncio.run(main_loop())
