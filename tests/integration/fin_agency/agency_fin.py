from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

# Import the Financial Research Agency agents
from financial_research_agency.PortfolioManager.PortfolioManager import portfolio_manager
from financial_research_agency.ReportGenerator.ReportGenerator import report_generator
from financial_research_agency.RiskAnalyst.RiskAnalyst import risk_analyst

from agency_swarm import Agency

load_dotenv()


def create_agency(
    load_threads_callback: Callable[[], list[dict[str, Any]]] | None = None,
    save_threads_callback: Callable[[list[dict[str, Any]]], None] | None = None,
) -> Agency:
    agency = Agency(
        portfolio_manager,
        report_generator,
        risk_analyst,
        communication_flows=[
            (portfolio_manager, risk_analyst),
            (risk_analyst, report_generator),
        ],
        shared_instructions="financial_research_agency/agency_manifesto.md",
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
    )

    return agency


if __name__ == "__main__":
    agency = create_agency()

    # test 1 message (optional)
    # async def main():
    #     response = await agency.get_response(
    #         "Search for machine learning tutorials and find detailed information about "
    #         "neural networks"
    #     )
    #     print(response)
    # asyncio.run(main())

    # run in terminal
    agency.terminal_demo()
