from agency_swarm import Agent, Agency

from agents.basic_agents.api_agents import (
    API_param_selector, param_selector, array_selector, API_filler, API_caller, param_filler, array_filler
)

from agents.cap_group_agents.IAM_service_group.cap_agents.AKSK_agent import AKSK_agent

from agents.basic_agents.api_agents.tools.SelectAPIParam import SelectAPIParam
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable
from agents.basic_agents.api_agents.tools.FillAPI import FillAPI
from agents.basic_agents.api_agents.tools.FillParamTable import FillParamTable

from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))

api_param_selector = API_param_selector.create_agent()
param_selector = param_selector.create_agent()
array_selector = array_selector.create_agent()

api_filler = API_filler.create_agent()
api_caller = API_caller.create_agent()
AKSK_agent = AKSK_agent.create_agent()
param_filler = param_filler.create_agent()
array_filler = array_filler.create_agent()

chart_graph = [
    api_param_selector,
    [param_selector, array_selector],

    api_filler,
    [api_filler, api_caller, AKSK_agent],
    [param_filler, array_filler],
    [array_filler, param_filler]
]

thread_strategy = {
    "always_new": [
        (SelectAPIParam, param_selector),
        (SelectParamTable, param_selector),
        (param_selector, array_selector),
        (FillAPI, param_filler),
        (FillParamTable, param_filler),
        (param_filler, array_filler),
        (array_filler, param_filler),
    ]
}

agency = Agency(
    agency_chart=chart_graph,
    thread_strategy=thread_strategy,
    temperature=0,
    max_prompt_tokens=25000
)

agency.run_demo()
# agency.run_demo()
