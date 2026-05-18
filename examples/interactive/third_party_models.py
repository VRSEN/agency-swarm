"""
This example showcases how you can:
1. Easily set up an agency that uses third-party models (Claude and Gemini) through LiteLLM.
2. Use their native tools (Gemini web search).
3. Combine them with unpatched OpenAI models.
4. Run a non-interactive smoke check for release testing.

Pre-requisites:
1. Set OPENAI_API_KEY for the strategy coordinator.
2. Set at least one third-party provider key:
    - ANTHROPIC_API_KEY for Claude models
    - GOOGLE_API_KEY for Gemini models
3. This example does not configure a Grok agent.
4. Install the Agency Swarm LiteLLM extra.

Run a non-interactive provider check by running:
`python examples/interactive/third_party_models.py --check`

Run a non-interactive Claude/Gemini smoke by running:
`python examples/interactive/third_party_models.py --smoke`

Run the agency TUI by running `python examples/interactive/third_party_models.py`
This will open the TUI for a startup validation agency with up to 3 agents:
1. strategy_agent - gpt agent coordinates and summarizes work of other agents.
2. market_research_agent - gemini agent that performs market research and competitive analysis.
3. technical_agent - claude agent that designs system architecture, generates MVP code, and provides technical implementation based on validated business requirements.
Missing optional third-party providers are skipped with a startup message.

At the start of the chat, you can ask the agent to validate a startup idea or build an MVP, for example:
"I have an idea for a SaaS tool that helps small businesses manage their social media content. Can you do a quick research and validate this idea?"
Then follow it up with:
"Propose a system architecture for this idea and stack for an MVP."
"""

import argparse
import asyncio
import os
import warnings

import litellm
from agents import ModelSettings
from dotenv import load_dotenv

from agency_swarm import Agency, Agent

# Suppress Pydantic deprecation warnings from litellm
warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv()


PROVIDERS = {
    "openai": ("StrategyAgent", "OPENAI_API_KEY"),
    "claude": ("TechnicalAgent", "ANTHROPIC_API_KEY"),
    "gemini": ("MarketResearchAgent", "GOOGLE_API_KEY"),
}


# Configure litellm to automatically add dummy tools for Anthropic
litellm.modify_params = True


strategy_agent = Agent(
    name="StrategyAgent",
    description="Synthesizes market research into actionable business strategies, product roadmaps, and coordinates between research and technical implementation.",
    instructions="""
    You are a strategic business consultant and product manager. Your role is to:

    1. **Strategy Synthesis**: Transform market research into clear business strategies and action plans
    2. **Product Planning**: Create detailed product roadmaps, feature prioritization, and MVP specifications
    3. **Business Model Design**: Develop revenue models, pricing strategies, and go-to-market plans
    4. **Coordination**: Bridge the gap between market insights and technical implementation
    5. **Risk Assessment**: Identify potential challenges and mitigation strategies

    When receiving market research, always:
    - Extract key insights and translate them into strategic decisions
    - Prioritize features based on market validation and technical feasibility
    - Create clear, actionable specifications for the technical team
    - Provide business justification for each recommendation
    - Consider both short-term MVP and long-term product vision

    Be decisive, practical, and always tie recommendations back to market data.
    """,
    model="openai/gpt-5.4-mini",
)

market_research_agent = Agent(
    name="MarketResearchAgent",
    description="Conducts real-time market research, competitive analysis, and validates business ideas using web search capabilities.",
    instructions="""
    You are a market research specialist with access to real-time web search. Your role is to:

    1. **Market Validation**: Research market demand, size, and growth potential for business ideas
    2. **Competitive Analysis**: Identify competitors, analyze their features, pricing, and positioning
    3. **Target Audience Research**: Find and analyze target demographics, user needs, and pain points
    4. **Trend Analysis**: Identify current market trends, emerging technologies, and opportunities
    5. **Pricing Research**: Analyze pricing strategies and market rates for similar products/services

    Always provide:
    - Current, factual data with sources
    - Quantitative metrics when available (market size, growth rates, etc.)
    - Specific competitor examples with their strengths/weaknesses
    - Clear recommendations based on research findings

    Use web search extensively to ensure your research is current and comprehensive.
    """,
    model="litellm/gemini/gemini-2.5-pro-preview-03-25",
    # Enable gemini's native web search tool
    model_settings=ModelSettings(
        truncation="auto", extra_body={"web_search_options": {"search_context_size": "medium"}}, temperature=0.1
    ),
)

technical_agent = Agent(
    name="TechnicalAgent",
    description="Designs system architecture, generates MVP code, and provides technical implementation based on validated business requirements.",
    instructions="""
    You are a senior full-stack developer and solution architect. Your role is to:

    1. **Architecture Design**: Create scalable, maintainable system architectures for MVPs
    2. **Code Generation**: Write clean, production-ready code following best practices
    3. **Technology Selection**: Choose appropriate tech stacks based on requirements and constraints
    4. **MVP Development**: Focus on rapid prototyping while maintaining code quality
    5. **Documentation**: Provide clear technical documentation and deployment guides

    When receiving strategic requirements, always:
    - Ask clarifying questions about technical constraints and preferences
    - Propose multiple technical approaches with pros/cons
    - Generate complete, runnable code examples
    - Include setup instructions and dependencies
    - Consider scalability, security, and maintainability from the start
    - Provide realistic timelines and development phases

    Prioritize speed of development for MVPs while ensuring the foundation can scale.
    """,
    model="litellm/anthropic/claude-sonnet-4-20250514",
    model_settings=ModelSettings(temperature=0.0),
)


def _has_key(provider: str) -> bool:
    """Return whether the provider's required environment key is set."""
    return bool(os.getenv(PROVIDERS[provider][1]))


def print_provider_status() -> None:
    """Print which providers this run can use."""
    print("Provider status:")
    for provider, (agent_name, env_var) in PROVIDERS.items():
        if _has_key(provider):
            print(f"- {agent_name} ({provider}): available")
        else:
            print(f"- {agent_name} ({provider}): skipped; set {env_var}")
    print("- Grok: not configured in this example")


def create_startup_validation_agency() -> Agency:
    """Create an agency using only providers that are available in the environment."""
    if not _has_key("openai"):
        raise RuntimeError("OPENAI_API_KEY is required for the StrategyAgent coordinator.")

    communication_flows = []
    if _has_key("gemini"):
        communication_flows.append(strategy_agent > market_research_agent)
    if _has_key("claude"):
        communication_flows.append(strategy_agent > technical_agent)

    if not communication_flows:
        raise RuntimeError("Set ANTHROPIC_API_KEY or GOOGLE_API_KEY to run a third-party model example.")

    return Agency(
        strategy_agent,  # Strategy agent acts as the coordinator
        communication_flows=communication_flows,
    )


def _resolve_smoke_provider(provider: str) -> str | None:
    """Resolve the provider to call for a non-interactive smoke run."""
    if provider != "auto":
        return provider if _has_key(provider) else None
    for candidate in ("claude", "gemini"):
        if _has_key(candidate):
            return candidate
    return None


async def run_smoke(provider: str) -> int:
    """Run one small model call against an available third-party provider."""
    print_provider_status()
    smoke_provider = _resolve_smoke_provider(provider)
    if smoke_provider is None:
        requested = "a third-party provider" if provider == "auto" else provider
        print(f"Smoke skipped: {requested} is not available in this environment.")
        return 1

    agency = create_startup_validation_agency()
    recipient_agent = PROVIDERS[smoke_provider][0]
    result = await agency.get_response(
        message="Reply with one short sentence confirming the third-party model smoke test is reachable.",
        recipient_agent=recipient_agent,
        additional_instructions="Do not call tools. Keep the answer under 20 words.",
    )
    print(f"Smoke provider: {smoke_provider}")
    print(f"Smoke response: {result.final_output}")
    return 0


def parse_args() -> argparse.Namespace:
    """Parse command-line options for interactive and non-interactive runs."""
    parser = argparse.ArgumentParser(description="Third-party model example with provider checks.")
    parser.add_argument("--check", action="store_true", help="Print available and skipped providers, then exit.")
    parser.add_argument(
        "--smoke", action="store_true", help="Send one non-interactive request to an available provider."
    )
    parser.add_argument(
        "--smoke-provider",
        choices=("auto", "claude", "gemini"),
        default="auto",
        help="Provider to call in --smoke mode. Defaults to the first available third-party provider.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the requested example mode."""
    args = parse_args()
    if args.check:
        print_provider_status()
        return 0
    if args.smoke:
        return asyncio.run(run_smoke(args.smoke_provider))

    print_provider_status()
    try:
        create_startup_validation_agency().tui()
    except RuntimeError as exc:
        print(f"Cannot start TUI: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
