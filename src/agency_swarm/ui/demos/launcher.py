class CopilotDemoLauncher:
    @staticmethod
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
    @staticmethod
    def start(agency_instance):
        """
        Executes agency in the terminal with autocomplete for recipient agent names.
        """
        import asyncio
        import logging
        import re
        import uuid

        from ..core.console_event_adapter import ConsoleEventAdapter

        logger = logging.getLogger(__name__)

        recipient_agents = [str(agent.name) for agent in agency_instance.entry_points]
        if not recipient_agents:
            raise ValueError(
                "Cannot start terminal demo without entry points. Please specify at least one entry point."
            )

        chat_id = f"run_demo_chat_{uuid.uuid4()}"

        event_converter = ConsoleEventAdapter()
        event_converter.console.rule()

        async def main_loop():
            while True:
                message = input("👤 USER: ")
                event_converter.console.rule()

                if not message:
                    continue

                recipient_agent = None
                # Check for agent mentions that start with @ at the beginning of text or after whitespace
                agent_mention_pattern = r"(?:^|\s)@(\w+)(?:\s|$)"
                agent_match = re.search(agent_mention_pattern, message)

                if agent_match:
                    mentioned_agent = agent_match.group(1)
                    try:
                        recipient_agent = [
                            agent for agent in recipient_agents if agent.lower() == mentioned_agent.lower()
                        ][0]
                        # Remove the agent mention from the message
                        message = re.sub(agent_mention_pattern, " ", message).strip()
                    except Exception:
                        logger.error(f"Recipient agent {mentioned_agent} not found.", exc_info=True)
                        continue

                # Default to first entry point if not specified
                if recipient_agent is None and agency_instance.entry_points:
                    recipient_agent = agency_instance.entry_points[0].name

                try:
                    response_buffer = ""
                    async for event in agency_instance.get_response_stream(
                        message=message,
                        recipient_agent=recipient_agent,
                        chat_id=chat_id,
                    ):
                        event_converter.openai_to_message_output(event, recipient_agent)
                        # Accumulate the response if it's a text delta
                        if hasattr(event, "data") and getattr(event.data, "type", None) == "response.output_text.delta":
                            response_buffer += event.data.delta
                    event_converter.console.rule()
                except Exception as e:
                    logger.error(f"Error during streaming: {e}", exc_info=True)

        try:
            asyncio.run(main_loop())
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting terminal demo...")
