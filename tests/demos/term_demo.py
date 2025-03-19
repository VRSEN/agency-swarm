import json
import sys

from agency_swarm.agency.agency import Agency
from agency_swarm.threads import Thread
from tests.ceo.ceo import Ceo

from .test_agent.test_agent import TestAgent
from .test_agent2.test_agent2 import TestAgent2

sys.path.insert(0, "../agency-swarm")


def custom_serializer(obj):
    if isinstance(obj, Thread):
        return {
            "agent": obj.agent.name,
            "recipient_agent": obj.recipient_agent.name,
        }
    raise TypeError(f"Type {type(obj)} not serializable")


def main():
    test_agent1 = TestAgent()
    test_agent2 = TestAgent2()
    ceo = Ceo()

    agency = Agency(
        [
            ceo,
            [ceo, test_agent1, test_agent2],
            [ceo, test_agent2],
        ]
    )

    print(json.dumps(agency.agents_and_threads, indent=4, default=custom_serializer))

    print("Ceo Tools: ", agency.ceo.tools)

    agency.run_demo()


if __name__ == "__main__":
    main()
