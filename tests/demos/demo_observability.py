import logging

from dotenv import load_dotenv

from agency_swarm import Agency, Agent
from agency_swarm.util import init_tracking

load_dotenv()
logger = logging.getLogger(__name__)


def main(tracker: str):
    # Initialize tracking based on the selected tracker
    init_tracking(tracker)

    # 1. Create agents with different roles
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

    # 2. Define the communication flows within the agency
    agency = Agency(
        [
            ceo,  # CEO is the entry point
            [ceo, developer],  # CEO can communicate with Developer
            [ceo, analyst],  # CEO can communicate with Analyst
            [developer, analyst],  # Developer can communicate with Analyst
        ],
        temperature=0.01,
    )

    # 3. Test the agency
    output = agency.get_completion("send a test message to Developer")
    logger.info(f"final output: {str(output)}")

    # 4. Run the demo with Gradio interface
    try:
        agency.demo_gradio()
    except KeyboardInterrupt:
        pass

    # 5. Run the CLI demo
    try:
        agency.run_demo()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    trackers = ["langfuse", "agentops"]  # "local", "langfuse", "agentops"
    for tracker in trackers:
        print(f"Running demo with {tracker.upper()} tracker")
        main(tracker)
