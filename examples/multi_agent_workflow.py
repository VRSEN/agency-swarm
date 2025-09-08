# examples/multi_agent_workflow.py
"""
Multi-Agent Collaboration Example with Validation

This example demonstrates and validates that multi-agent communication works correctly
in Agency Swarm. It creates a financial analysis workflow where:

1. PortfolioManager (orchestrator) - Gathers market data and coordinates analysis
2. RiskAnalyst (specialist) - Analyzes investment risks using specialized tools
3. ReportGenerator (specialist) - Formats professional investment reports

The example also utilizes the output_type parameter to improve the structure of agents responses.

Run with: python examples/multi_agent_workflow.py
"""

import asyncio
import logging
import os
import sys
from typing import Any

from pydantic import BaseModel, Field

# Configure basic logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent, RunContextWrapper, function_tool  # noqa: E402


# --- Structured Output Types ---
class RiskAssessment(BaseModel):
    risk_level: str = Field(..., description="Overall risk level (Low/Moderate/High)")
    risk_score: str = Field(..., description="Risk score out of 10")
    key_risks: list[str] = Field(..., description="List of key risk factors")
    recommendation: str = Field(..., description="Risk-based recommendation")


class InvestmentReport(BaseModel):
    executive_summary: str = Field(..., description="Brief executive summary")
    market_position: str = Field(..., description="Current market position analysis")
    risk_analysis: str = Field(..., description="Risk analysis summary")
    final_recommendation: str = Field(..., description="Final investment recommendation")


# --- Global tracking for validation ---
tool_calls_made = []
agent_interactions = []


# --- Simple Tools ---
@function_tool()
async def fetch_market_data(wrapper: RunContextWrapper[Any], symbol: str) -> str:
    """Fetches basic market data for a stock symbol."""
    print(f"--- TOOL: fetch_market_data called for {symbol} ---")
    tool_calls_made.append(f"fetch_market_data:{symbol}")
    await asyncio.sleep(0.3)  # Simulate API call
    return f"Retrieved market data for {symbol}: Price $175.43, Market Cap $2.85T, P/E 28.5, Rating: Buy"


@function_tool()
async def analyze_risk_factors(wrapper: RunContextWrapper[Any], symbol: str) -> str:
    """Analyzes risk factors for a stock."""
    print(f"--- TOOL: analyze_risk_factors called for {symbol} ---")
    tool_calls_made.append(f"analyze_risk_factors:{symbol}")
    await asyncio.sleep(0.4)  # Simulate analysis
    return f"Risk analysis for {symbol}: High P/E suggests overvaluation risk, Beta 1.29 indicates volatility, Strong balance sheet provides stability"


@function_tool()
async def format_professional_report(wrapper: RunContextWrapper[Any], content: str) -> str:
    """Formats content into a professional investment report."""
    print("--- TOOL: format_professional_report called ---")
    tool_calls_made.append("format_professional_report")
    await asyncio.sleep(0.2)  # Simulate formatting
    return f"Professional report formatted with: {content[:50]}..."


# --- Define Agents ---
portfolio_manager = Agent(
    name="PortfolioManager",
    instructions="""You orchestrate investment research by:
    1. Using fetch_market_data tool to get financial metrics
    2. Delegating risk analysis to RiskAnalyst
    3. Delegating report formatting to ReportGenerator
    4. Compiling final investment recommendation

    Always gather data first, then delegate analysis, then request formatting.""",
    tools=[fetch_market_data],
    output_type=str,  # Returns final recommendation
)

risk_analyst = Agent(
    name="RiskAnalyst",
    instructions="""You specialize in investment risk analysis. When given market data:
    1. Use analyze_risk_factors tool to evaluate risks
    2. Assess volatility, valuation, and market position
    3. Return structured risk assessment

    Focus on identifying key risks and providing clear risk scoring.""",
    tools=[analyze_risk_factors],
    output_type=RiskAssessment,  # Structured risk output
)

report_generator = Agent(
    name="ReportGenerator",
    instructions="""You create professional investment reports. When given analysis:
    1. Use format_professional_report tool for formatting assistance
    2. Structure information with clear sections
    3. Return professional investment report

    Focus on clear, executive-ready presentation.""",
    tools=[format_professional_report],
    output_type=InvestmentReport,  # Structured report output
)


# --- Create Agency ---
agency = Agency(
    portfolio_manager,  # Entry point and orchestrator
    communication_flows=[
        portfolio_manager > risk_analyst,
        portfolio_manager > report_generator,
    ],
    shared_instructions="Provide accurate, professional financial analysis.",
)


# Helper function to visualize send message arguments
def print_send_message_history(agency, agent_name: str) -> None:
    agent_messages = agency._agent_contexts[agent_name].thread_manager._store.messages
    call_ids = []
    print("Message history for inter-agent communications:")
    i = 1
    for message in agent_messages:
        if "parent_run_id" not in message or "role" not in message:
            continue
        if message["role"] == "user" and message["agent"] is not None and message["callerAgent"] is not None:
            call_ids.append(message["parent_run_id"])
            print(f"{i}. {message['callerAgent']} -> {message['agent']} message: {message['content']}\n")
            i += 1
        elif message["role"] == "assistant" and message["parent_run_id"] in call_ids:
            print(f"{i}. {message['agent']} -> {message['callerAgent']} response: {message['content'][0]['text']}\n")
            i += 1


async def run_workflow():
    print("\n--- Investment Research Platform Demo ---")
    print("Portfolio Manager orchestrates by calling specialist agents and compiling results.\n")

    # Reset tracking
    global tool_calls_made, agent_interactions
    tool_calls_made = []
    agent_interactions = []

    stock_symbol = "AAPL"
    print(f"Client Request: Analyze investment opportunity for {stock_symbol}")

    response = await agency.get_response(
        message=f"Provide comprehensive investment analysis for {stock_symbol}. Get market data, risk assessment, and professional report."
    )

    print_send_message_history(agency, "PortfolioManager")

    print("\nFinal Investment Analysis:")
    print(f"{response.final_output}")
    print(f"\nCompleted in {len(response.new_items)} agent actions.")


if __name__ == "__main__":
    success = asyncio.run(run_workflow())
