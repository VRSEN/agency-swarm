from agency_swarm import Agent, Agency

from agents.basic_agents.api_agents import (
    API_param_selector, param_selector, array_selector, API_filler, API_caller, param_filler, array_filler
)


from agents.cap_group_agents import param_asker
from agents.basic_agents.api_agents.tools.SelectAPIParam import SelectAPIParam
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable
from agents.basic_agents.api_agents.tools.FillAPI import FillAPI
from agents.basic_agents.api_agents.tools.FillParamTable import FillParamTable
from agents.cap_group_agents.CLUSTER_group import CLUSTER_manager
from agents.cap_group_agents.CLUSTER_group.cap_agents.CLUSTER_lifecycle_agent import CLUSTER_lifecycle_agent


from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))

CLUSTER_manager = CLUSTER_manager.create_agent()
CLUSTER_lifecycle_agent = CLUSTER_lifecycle_agent.create_agent()
param_asker = param_asker.create_agent()

chart_graph = [
    CLUSTER_manager,
    [CLUSTER_manager, param_asker],
]

agency = Agency(
    agency_chart=chart_graph,
    temperature=0,
    max_prompt_tokens=25000
)

agency.demo_gradio()
# agency.run_demo()
