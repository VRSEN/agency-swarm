import argparse
import os


def main():
    parser = argparse.ArgumentParser(description='Create agent template.')

    subparsers = parser.add_subparsers(dest='command', help='Create agent template.')
    subparsers.required = True

    # create-agent-template
    create_parser = subparsers.add_parser('create-agent-template', help='Create agent template folder locally.')
    create_parser.add_argument('--path', type=str, default="./", help='Path to create agent folder.')
    create_parser.add_argument('--use_txt', action='store_true', default=False,
                               help='Use txt instead of md for instructions and manifesto.')
    create_parser.add_argument('--name', type=str, help='Name of agent.')
    create_parser.add_argument('--description', type=str, help='Description of agent.')

    # genesis-agency
    genesis_parser = subparsers.add_parser('genesis', help='Start genesis agency.')
    genesis_parser.add_argument('--openai_key', default=None, type=str, help='OpenAI API key.')

    args = parser.parse_args()

    if args.command == "create-agent-template":
        from agency_swarm.util import create_agent_template
        create_agent_template(args.name, args.description, args.path, args.use_txt)
    elif args.command == "genesis":
        if not os.getenv('OPENAI_API_KEY') and not args.openai_key:
            print("OpenAI API key not set. "
                  "Please set it with --openai_key argument or by setting OPENAI_API_KEY environment variable.")
            return

        if args.openai_key:
            from agency_swarm import set_openai_key
            set_openai_key(args.openai_key)

        from agency_swarm.agency.genesis import GenesisAgency
        agency = GenesisAgency()
        agency.run_demo()


if __name__ == "__main__":
    main()
