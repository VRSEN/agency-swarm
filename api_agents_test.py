from agency_swarm import Agent, Agency
from agency_swarm.threads import Thread

from agents.cap_group_agents import API_entrance_agent
from agents.cap_group_agents import param_asker_nocontext

from agents.basic_agents.api_agents import (
    API_param_selector, param_selector, array_selector, param_inspector
)

from agents.basic_agents.api_agents.tools.CheckParamRequired import CheckParamRequired
from agents.basic_agents.api_agents.tools.SelectAPIParam import SelectAPIParam
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os
import json

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))

API_entrance_agent_instance = API_entrance_agent.create_agent()
param_asker_instance = param_asker_nocontext.create_agent()

API_param_selector_instance = API_param_selector.create_agent()
array_selector_instance = array_selector.create_agent()
param_selector_instance = param_selector.create_agent()
param_inspector_instance = param_inspector.create_agent()

def run_agency(user_requirement: str, api_name: str):
    chart_graph = [
        API_entrance_agent_instance,
        [API_entrance_agent_instance, API_param_selector_instance],
        [API_entrance_agent_instance, param_asker_instance],
        param_inspector_instance,
        param_selector_instance,
        array_selector_instance,
    ]
    thread_strategy = {
        "always_new": [
            (SelectAPIParam, param_selector_instance),
            (SelectParamTable, param_selector_instance),
            (param_selector_instance, array_selector_instance),
            (CheckParamRequired, array_selector_instance),
        ]
    }
    agency = Agency(
        agency_chart=chart_graph,
        thread_strategy=thread_strategy,
        temperature=0.5,
        max_prompt_tokens=25000
    )

    # test: Gradio I/O
    agency.demo_gradio()

    # code I/O
    # API_entrance_thread = Thread(agency.user, API_entrance_agent_instance)
    # message_json = {
    #     "user_requirement": user_requirement,
    #     "api_name": api_name
    # }
    # result_str = agency.json_get_completion(API_entrance_thread, message=json.dumps(message_json, ensure_ascii=False, indent=4))
    # print(result_str)

if __name__ == "__main__":
    run_agency("", "")
