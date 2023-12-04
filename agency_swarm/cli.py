import argparse

from agency_swarm.util import create_agent_template


def main():
    parser = argparse.ArgumentParser(description='Create agent template.')

    subparsers = parser.add_subparsers(dest='create_template', help='Create agent template.')
    subparsers.required = True

    create_parser = subparsers.add_parser('create-agent-template', help='Create agent template folder locally.')
    create_parser.add_argument('--path', type=str, default="./", help='Path to create agent folder.')
    create_parser.add_argument('--use_txt', action='store_true', default=False,
                               help='Use txt instead of md for instructions and manifesto.')
    create_parser.add_argument('--name', type=str, help='Name of agent.')
    create_parser.add_argument('--description', type=str, help='Description of agent.')

    args = parser.parse_args()

    if args.create_template == "create-agent-template":
        create_agent_template(args.name, args.description, args.path, args.use_txt)


if __name__ == "__main__":
    main()
