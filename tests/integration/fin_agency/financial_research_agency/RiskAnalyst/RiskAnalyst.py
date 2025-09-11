from agency_swarm import Agent

risk_analyst = Agent(
    name="RiskAnalyst",
    description=(
        "Specialized agent focused on investment risk assessment, analyzing "
        "market volatility, valuation metrics, competitive positioning, and "
        "regulatory risks."
    ),
    instructions="./instructions.md",
    tools_folder="./tools",
    model="gpt-4.1",
)
