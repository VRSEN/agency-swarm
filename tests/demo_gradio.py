import sys

import gradio as gr

from agency_swarm import set_openai_key

sys.path.insert(0, '../agency-swarm')

from agency_swarm.agency.agency import Agency
from tests.ceo.ceo import Ceo
from tests.test_agent.test_agent import TestAgent
from tests.test_agent2.test_agent2 import TestAgent2

set_openai_key("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")

test_agent1 = TestAgent()
test_agent2 = TestAgent2()
ceo = Ceo()

agency = Agency([
    ceo,
    [ceo, test_agent1, test_agent2],
    [ceo, test_agent2],
], shared_instructions="./manifesto.md")


agency.demo_gradio(height=1500)

