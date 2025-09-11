from agency_swarm import Agent

portfolio_manager = Agent(
    name="PortfolioManager",
    description=(
        "Lead orchestrator responsible for coordinating the entire investment research process, "
        "from initial data gathering to final report delivery."
    ),
    instructions="./instructions.md",
    tools_folder="./tools",
    model="gpt-4.1",
)
