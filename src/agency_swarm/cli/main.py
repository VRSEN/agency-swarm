"""Main CLI entry point for Agency Swarm."""

import argparse
import sys

from agency_swarm.utils.create_agent_template import create_agent_template

from .import_tool import import_tool_command
from .migrate_agent import migrate_agent_command


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="agency-swarm",
        description="Agency Swarm CLI tools",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create-agent-template command
    create_agent_parser = subparsers.add_parser(
        "create-agent-template", help="Create a new agent template with the standard folder structure"
    )
    create_agent_parser.add_argument("name", help="Name of the agent (e.g., 'Data Analyst', 'Content Writer')")
    create_agent_parser.add_argument("--description", help="Description of the agent's role and responsibilities")
    create_agent_parser.add_argument("--model", default="gpt-5.2", help="OpenAI model to use (default: gpt-5.2)")
    create_agent_parser.add_argument(
        "--reasoning", choices=["low", "medium", "high"], help="Reasoning effort level for the model"
    )
    create_agent_parser.add_argument("--max-tokens", type=int, help="Maximum completion tokens")
    create_agent_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Model temperature (default: 0.3 for non-reasoning models, ignored for reasoning models)",
    )
    create_agent_parser.add_argument("--instructions", help="Custom instructions for the agent (optional)")
    create_agent_parser.add_argument(
        "--use-txt", action="store_true", help="Use .txt extension for instructions instead of .md"
    )
    create_agent_parser.add_argument(
        "--path", default="./", help="Output directory for the agent template (default: current directory)"
    )
    # Migrate agent command
    migrate_parser = subparsers.add_parser(
        "migrate-agent",
        help="Generate agent from assistants API settings.json",
        usage="agency-swarm migrate-agent path_to_settings.json [--output-dir DIR]",
    )
    migrate_parser.add_argument(
        "settings_file",
        help="Path to the settings.json file",
    )
    migrate_parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for the generated agent (default: current directory)",
    )

    # Import tool command
    import_tool_parser = subparsers.add_parser(
        "import-tool",
        help="Import a built-in tool into the current project",
        usage="agency-swarm import-tool [TOOL_NAME] [--destination DIR] [--list]",
    )
    import_tool_parser.add_argument(
        "tool_name",
        nargs="?",
        help="Name of the built-in tool to import (e.g., 'IPythonInterpreter', 'PersistentShellTool')",
    )
    import_tool_parser.add_argument(
        "--directory",
        default="./tools",
        help="Destination directory for the tool (default: ./tools)",
    )
    import_tool_parser.add_argument(
        "--list",
        action="store_true",
        dest="list_tools",
        help="List all available built-in tools",
    )

    args = parser.parse_args()

    if args.command == "migrate-agent":
        exit_code = migrate_agent_command(args.settings_file, args.output_dir)
        sys.exit(exit_code)
    elif args.command == "import-tool":
        exit_code = import_tool_command(args.tool_name, args.directory, args.list_tools)
        sys.exit(exit_code)
    elif args.command == "create-agent-template":
        try:
            success = create_agent_template(
                agent_name=args.name,
                agent_description=args.description,
                model=args.model,
                reasoning=args.reasoning,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                instructions=args.instructions,
                use_txt=args.use_txt,
                path=args.path,
            )
        except Exception as exc:  # pragma: no cover - defensive guardrail
            print(f"\033[91mERROR: {exc}\033[0m", file=sys.stderr)
            raise SystemExit(1) from exc

        if not success:
            raise SystemExit(1)
    elif args.command is None:
        parser.print_help()
    else:
        print(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
