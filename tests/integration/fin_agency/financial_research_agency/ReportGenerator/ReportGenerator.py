from agency_swarm import Agent

report_generator = Agent(
    name="ReportGenerator",
    description=(
        "Professional report formatting specialist responsible for creating executive-ready "
        "investment reports with proper structure and clear presentation."
    ),
    instructions="./instructions.md",
    tools_folder="./tools",
    model="gpt-4.1",
)
