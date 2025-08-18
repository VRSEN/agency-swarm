from dotenv import load_dotenv

# Import the Search Agency agents
from financial_research_agency.PortfolioManager.PortfolioManager import PortfolioManager
from financial_research_agency.ReportGenerator.ReportGenerator import ReportGenerator
from financial_research_agency.RiskAnalyst.RiskAnalyst import RiskAnalyst

from agency_swarm import Agency

load_dotenv()


def create_agency(load_threads_callback=None):
    portfolio_manager = PortfolioManager()
    report_generator = ReportGenerator()
    risk_analyst = RiskAnalyst()

    agency = Agency(
        portfolio_manager,
        report_generator,
        risk_analyst,
        communication_flows=[
            (portfolio_manager, report_generator),
            (portfolio_manager, risk_analyst),
            (report_generator, risk_analyst),
        ],
        # ],
        shared_instructions="financial_research_agency/agency_manifesto.md",
        load_threads_callback=load_threads_callback,
    )

    return agency


if __name__ == "__main__":
    agency = create_agency()

    # test 1 message (optional)
    # async def main():
    #     response = await agency.get_response("Search for machine learning tutorials and find detailed information about neural networks")
    #     print(response)
    # asyncio.run(main())

    # run in terminal
    agency.terminal_demo()
