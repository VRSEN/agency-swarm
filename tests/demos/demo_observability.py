from dotenv import load_dotenv

load_dotenv()

from agency_swarm import Agency, Agent  # noqa
from agency_swarm.util import init_tracking  # noqa


def main():
    # Set the tracker type
    TRACKER = "local"
    # To use Langfuse, uncomment the next line
    # TRACKER = "langfuse"

    # Initialize tracking based on the selected tracker
    init_tracking(TRACKER)

    # Create agents with different roles
    ceo = Agent(
        name="CEO",
        description="Manages projects and coordinates between team members",
        temperature=0.5,
    )

    developer = Agent(
        name="Developer",
        description="Implements technical solutions and writes code",
        temperature=0.3,
    )

    analyst = Agent(
        name="Data Analyst",
        description="Analyzes data and provides insights",
        temperature=0.4,
    )

    # Define the communication flows within the agency
    agency = Agency(
        [
            ceo,  # CEO is the entry point
            [ceo, developer],  # CEO can communicate with Developer
            [ceo, analyst],  # CEO can communicate with Analyst
            [developer, analyst],  # Developer can communicate with Analyst
        ]
    )

    # Run the demo with Gradio interface
    agency.demo_gradio()
    # If you prefer to run the CLI demo, uncomment the next line
    # agency.run_demo()


if __name__ == "__main__":
    main()
