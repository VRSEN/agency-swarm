"""Main CLI entry point for Agency Swarm."""

import argparse

from dotenv import load_dotenv


def main() -> None:
    """Main CLI entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="agency-swarm",
        description="Agency Swarm CLI tools",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create-agent-template command
    create_agent_parser = subparsers.add_parser(
        "create-agent-template",
        help="Create a new agent template with the standard folder structure"
    )
    create_agent_parser.add_argument(
        "name",
        help="Name of the agent (e.g., 'Data Analyst', 'Content Writer')"
    )
    create_agent_parser.add_argument(
        "--description",
        help="Description of the agent's role and responsibilities"
    )
    create_agent_parser.add_argument(
        "--model",
        default="gpt-4.1",
        help="OpenAI model to use (default: gpt-4.1)"
    )
    create_agent_parser.add_argument(
        "--reasoning",
        choices=["low", "medium", "high"],
        help="Reasoning effort level for the model"
    )
    create_agent_parser.add_argument(
        "--max-tokens",
        type=int,
        help="Maximum completion tokens"
    )
    create_agent_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Model temperature (default: 0.3 for non-reasoning models, ignored for reasoning models)"
    )
    create_agent_parser.add_argument(
        "--instructions",
        help="Custom instructions for the agent (optional)"
    )
    create_agent_parser.add_argument(
        "--use-txt",
        action="store_true",
        help="Use .txt extension for instructions instead of .md"
    )
    create_agent_parser.add_argument(
        "--path",
        default="./",
        help="Output directory for the agent template (default: current directory)"
    )

    args = parser.parse_args()

    if args.command == "migrate-agent":
        pass
    elif args.command == "create-agent-template":
        from agency_swarm.utils.create_agent_template import create_agent_template

        create_agent_template(
            agent_name=args.name,
            agent_description=args.description,
            model=args.model,
            reasoning=args.reasoning,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            instructions=args.instructions,
            use_txt=args.use_txt,
            path=args.path
        )
    elif args.command is None:
        parser.print_help()
    else:
        print(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
