import json
import sys

from agency_swarm.agency.agency import Agency, Agent
from agency_swarm.threads import Thread

sys.path.insert(0, "../agency-swarm")


def custom_serializer(obj):
    if isinstance(obj, Thread):
        return {
            "agent": obj.agent.name,
            "recipient_agent": obj.recipient_agent.name,
        }
    raise TypeError(f"Type {type(obj)} not serializable")

ceo = Agent(
    name="CEO",
    description="Responsible for client communication, task planning and management.",
    instructions="Test agent",
)


test_agent1 = Agent(
    name="test_agent1",
    description="Responsible for testing.",
    instructions="Test agent",
)

test_agent2 = Agent(
    name="test_agent2",
    description="Responsible for testing.",
    instructions="Test agent",
)

def main():

    agency = Agency(
        [
            ceo,
            [ceo, test_agent1],
            [ceo, test_agent2],
        ],
    )

    print(json.dumps(agency.agents_and_threads, indent=4, default=custom_serializer))

    agency.run_demo()


if __name__ == "__main__":
    main()
