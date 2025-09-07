"""
This example showcases how you can:
1. Easily setup an agency that utilizes open-source models
2. Use their native tools (anthropic's web search).
3. Combine them with unpatched models (to allow for oai's hosted tool usage)

Pre-requisites:
1. Following env variables for set for respective models in the `.env` file:
    - ANTHROPIC_API_KEY for claude models
    - GOOGLE_API_KEY for gemini models
    - XAI_API_KEY for grok models
    - OPENAI_API_KEY for openai models
2. Install openai-agents optional litellm package by running `pip install 'openai-agents[litellm]'`
3. Install litellm[proxy] separatelly by running `pip install 'litellm[proxy]'`

Run the agency by running `python examples/open_source_models.py`
This will open a terminal demo of an startup validation agency with 3 agents:
1. strategy_agent - gpt agent coordinates and summarizes work of other agents.
2. market_research_agent - gemini agent that performs market research and competitive analysis.
3. technical_agent - claude agent that designs system architecture, generates MVP code, and provides technical implementation based on validated business requirements.

At the start of the chat, you can ask the agent to validate a startup idea or build an MVP, for example:
"I have an idea for a SaaS tool that helps small businesses manage their social media content. Can you do a quick research and validate this idea?"
Then follow it up with:
"Propose a system architecture for this idea and stack for an MVP."
"""

import warnings

import litellm
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv

from agency_swarm import Agency, Agent

# Suppress Pydantic deprecation warnings from litellm
warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv()


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
    model="openai/gpt-4.1",  # gpt-5 provides better results, but the example will take too long to run
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
    model=LitellmModel(model="gemini/gemini-2.5-pro-preview-03-25"),
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
    model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
    model_settings=ModelSettings(temperature=0.0),
)

agency = Agency(
    strategy_agent,  # Strategy agent acts as the coordinator
    communication_flows=[
        (strategy_agent > market_research_agent),  # Strategy requests market research
        (strategy_agent > technical_agent),  # Strategy provides requirements to technical agent
    ],
)

if __name__ == "__main__":
    agency.terminal_demo()
