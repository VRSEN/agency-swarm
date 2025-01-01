import logging

from dotenv import load_dotenv

from agency_swarm import Agency, Agent
from agency_swarm.util import init_tracking

load_dotenv()
logger = logging.getLogger(__name__)


def main():
    # Set the tracker type
    # TRACKER = "local"
    # TRACKER = "agentops"
    TRACKER = "langfuse"

    # Initialize tracking based on the selected tracker
    init_tracking(TRACKER)

    # Create agents with different roles
    ceo = Agent(
        name="CEO",
        description="Manages projects and coordinates between team members",
    )

    developer = Agent(
        name="Developer",
        description="Implements technical solutions and writes code",
    )

    analyst = Agent(
        name="Data Analyst",
        description="Analyzes data and provides insights",
    )

    # Define the communication flows within the agency
    agency = Agency(
        [
            ceo,  # CEO is the entry point
            [ceo, developer],  # CEO can communicate with Developer
            [ceo, analyst],  # CEO can communicate with Analyst
            [developer, analyst],  # Developer can communicate with Analyst
        ],
        temperature=0.01,
    )

    # output = agency.get_completion("send a test message to Developer")
    # logger.info(f"final output: {str(output)}")

    # Run the demo with Gradio interface
    agency.demo_gradio()
    # If you prefer to run the CLI demo, uncomment the next line
    # agency.run_demo()


if __name__ == "__main__":
    main()
