from agency_swarm import Agent, Agency

from agents.basic_agents.api_agents import (
    API_param_selector, param_selector, array_selector, param_inspector
)

from agents.cap_group_agents.IAM_service_group.cap_agents.AKSK_agent import AKSK_agent

from agents.basic_agents.api_agents.tools.SelectAPIParam import SelectAPIParam
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))

api_param_selector = API_param_selector.create_agent()
param_selector = param_selector.create_agent()
array_selector = array_selector.create_agent()
param_inspector = param_inspector.create_agent()

AKSK_agent = AKSK_agent.create_agent()

chart_graph = [
    api_param_selector,
    param_inspector,
    [param_selector, array_selector],

    [AKSK_agent],
]

thread_strategy = {
    "always_new": [
        (SelectAPIParam, param_selector),
        (SelectParamTable, param_selector),
        (param_selector, array_selector),
    ]
}

agency = Agency(
    agency_chart=chart_graph,
    thread_strategy=thread_strategy,
    temperature=0,
    max_prompt_tokens=25000
)

agency.demo_gradio()
# agency.run_demo()
