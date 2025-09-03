from agency_swarm import Agent


class RiskAnalyst(Agent):
    def __init__(self):
        super().__init__(
            name="RiskAnalyst",
            description=(
                "Specialized agent focused on investment risk assessment, analyzing "
                "market volatility, valuation metrics, competitive positioning, and "
                "regulatory risks."
            ),
            instructions="./instructions.md",
            tools_folder="./tools",
            model="gpt-5-mini",
        )
