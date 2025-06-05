# examples/multi_agent_workflow.py
"""
Multi-Agent Collaboration Example with Validation

This example demonstrates and validates that multi-agent communication works correctly
in Agency Swarm. It creates a financial analysis workflow where:

1. PortfolioManager (orchestrator) - Gathers market data and coordinates analysis
2. RiskAnalyst (specialist) - Analyzes investment risks using specialized tools
3. ReportGenerator (specialist) - Formats professional investment reports

The validation system confirms:
✅ All required tools are called by the appropriate agents
✅ Information flows between agents (each agent's expertise appears in final output)
✅ Multiple conversation steps occur (indicating agent-to-agent communication)
✅ Final output is comprehensive and includes contributions from all agents

Run with: python examples/multi_agent_workflow.py
"""

import asyncio
import logging
import os
import sys
from typing import Any

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent  # noqa: E402


# --- Structured Output Types ---
class MarketData(BaseModel):
    symbol: str = Field(..., description="Stock symbol")
    current_price: float = Field(..., description="Current stock price")
    market_cap: str = Field(..., description="Market capitalization")
    pe_ratio: float = Field(..., description="Price-to-earnings ratio")
    analyst_rating: str = Field(..., description="Overall analyst rating")


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
        (portfolio_manager, risk_analyst),
        (portfolio_manager, report_generator),
    ],
    shared_instructions="Provide accurate, professional financial analysis.",
)


def validate_multi_agent_collaboration(response, stock_symbol: str) -> bool:
    """Validate that multi-agent collaboration actually occurred."""
    print("\n" + "=" * 60)
    print("VALIDATING MULTI-AGENT COLLABORATION")
    print("=" * 60)

    success_criteria = []

    # 1. Check that all expected tools were called
    expected_tools = [
        f"fetch_market_data:{stock_symbol}",
        f"analyze_risk_factors:{stock_symbol}",
        "format_professional_report",
    ]

    tools_success = True
    for expected_tool in expected_tools:
        if expected_tool in tool_calls_made:
            print(f"✅ Tool called: {expected_tool}")
        else:
            print(f"❌ Missing tool call: {expected_tool}")
            tools_success = False
    success_criteria.append(("All required tools called", tools_success))

    # 2. Check that response contains data from each agent's domain
    final_output = response.final_output.lower() if response and response.final_output else ""

    # Market data indicators (from PortfolioManager's fetch_market_data)
    market_data_present = any(
        indicator in final_output for indicator in ["175.43", "$175", "2.85t", "28.5", "p/e", "market cap"]
    )
    print(
        f"✅ Market data present: {market_data_present}"
        if market_data_present
        else f"❌ Market data missing: {market_data_present}"
    )
    success_criteria.append(("Market data in final output", market_data_present))

    # Risk analysis indicators (from RiskAnalyst)
    risk_analysis_present = any(
        indicator in final_output for indicator in ["risk", "volatility", "beta", "overvaluation", "moderate", "6"]
    )
    print(
        f"✅ Risk analysis present: {risk_analysis_present}"
        if risk_analysis_present
        else f"❌ Risk analysis missing: {risk_analysis_present}"
    )
    success_criteria.append(("Risk analysis in final output", risk_analysis_present))

    # Professional report structure (from ReportGenerator)
    report_structure_present = any(
        indicator in final_output
        for indicator in ["executive summary", "market position", "final recommendation", "investment"]
    )
    print(
        f"✅ Professional report structure present: {report_structure_present}"
        if report_structure_present
        else f"❌ Report structure missing: {report_structure_present}"
    )
    success_criteria.append(("Professional report structure", report_structure_present))

    # 3. Check that we have multiple conversation steps (indicating agent-to-agent communication)
    steps_count = len(response.new_items) if response and response.new_items else 0
    multiple_steps = steps_count >= 5  # Should have multiple back-and-forth communications
    print(
        f"✅ Multiple conversation steps ({steps_count}): {multiple_steps}"
        if multiple_steps
        else f"❌ Insufficient conversation steps ({steps_count}): {multiple_steps}"
    )
    success_criteria.append(("Multiple conversation steps", multiple_steps))

    # 4. Check that final output is comprehensive (not just from one agent)
    output_length = len(final_output) if final_output else 0
    comprehensive_output = output_length > 500  # Should be substantial if all agents contributed
    print(
        f"✅ Comprehensive output ({output_length} chars): {comprehensive_output}"
        if comprehensive_output
        else f"❌ Output too brief ({output_length} chars): {comprehensive_output}"
    )
    success_criteria.append(("Comprehensive output", comprehensive_output))

    # Calculate overall success
    passed_criteria = sum(1 for _, success in success_criteria if success)
    total_criteria = len(success_criteria)

    print(f"\nCRITERIA SUMMARY: {passed_criteria}/{total_criteria} passed")
    for criterion_name, success in success_criteria:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {criterion_name}")

    overall_success = passed_criteria == total_criteria

    print("\n" + "=" * 60)
    if overall_success:
        print("🎉 SUCCESS: Multi-agent collaboration is working correctly!")
        print("   - All agents participated in the workflow")
        print("   - Information flowed between agents successfully")
        print("   - Each agent contributed unique expertise to the final result")
    else:
        print("💥 FAILURE: Multi-agent collaboration has issues!")
        print(f"   - Only {passed_criteria}/{total_criteria} validation criteria passed")
        print("   - Agents may not be communicating properly")
    print("=" * 60)

    return overall_success


async def run_workflow():
    print("\n--- Investment Research Platform Demo ---")
    print("Portfolio Manager orchestrates by calling specialist agents and compiling results.\n")

    # Reset tracking
    global tool_calls_made, agent_interactions
    tool_calls_made = []
    agent_interactions = []

    stock_symbol = "AAPL"
    print(f"Client Request: Analyze investment opportunity for {stock_symbol}")

    try:
        response = await agency.get_response(
            message=f"Provide comprehensive investment analysis for {stock_symbol}. Get market data, risk assessment, and professional report."
        )

        if response:
            print("\nFinal Investment Analysis:")
            print(f"{response.final_output}")
            print(f"\nCompleted with {len(response.new_items)} research steps.")

            # Validate the collaboration
            validation_success = validate_multi_agent_collaboration(response, stock_symbol)

            return validation_success
        else:
            print("\n💥 FAILURE: Analysis failed to produce a response.")
            return False

    except Exception as e:
        logging.error(f"💥 FAILURE: Error during analysis: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        success = asyncio.run(run_workflow())
        exit_code = 0 if success else 1
        print(f"\nExiting with code: {exit_code}")
        sys.exit(exit_code)
