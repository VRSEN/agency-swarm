import logging

from dotenv import load_dotenv

from agency_swarm import Agency, Agent
from agency_swarm.util import init_tracking, stop_tracking

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def setup_agency():
    """Create agents and configure the agency with communication flows"""
    ceo = Agent(
        name="CEO",
        instructions="You are the CEO.",
        description="Manages projects and coordinates between team members",
    )

    developer = Agent(
        name="Developer",
        instructions="You are the Developer.",
        description="Implements technical solutions and writes code",
    )

    analyst = Agent(
        name="Data Analyst",
        instructions="You are the Data Analyst.",
        description="Analyzes data and provides insights",
    )

    return Agency(
        [
            ceo,  # CEO is the entry point
            [ceo, developer],  # CEO can communicate with Developer
            [ceo, analyst],  # CEO can communicate with Analyst
            [developer, analyst],  # Developer can communicate with Analyst
        ],
        temperature=0.01,
    )


def run_demo():
    """Run the observability demo"""
    init_tracking("langfuse")
    init_tracking("local")

    agency = setup_agency()

    output = agency.get_completion("Send a test message to Developer")
    logger.info(f"Response: {str(output)}")

    stop_tracking()
    print(
        "\nDemo completed. Check Langfuse dashboard and local SQLite database for the results."
    )


if __name__ == "__main__":
    run_demo()
