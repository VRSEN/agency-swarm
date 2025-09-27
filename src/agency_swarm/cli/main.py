"""Main CLI entry point for Agency Swarm."""

import argparse
import sys

from .migrate_agent import migrate_agent_command


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="agency-swarm",
        description="Agency Swarm CLI tools",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

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

    args = parser.parse_args()

    if args.command == "migrate-agent":
        migrate_agent_command(args.settings_file, args.output_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
