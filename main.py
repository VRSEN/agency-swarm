from agency_swarm import Agent, Agency

from agents import leader
from agents.task_planner import task_planner
from agents.task_planner import inspector
from agents.task_planner.scheduler import scheduler
from agents import inspector_capability
from agents import capability_planner

from agents.subtask_planner import subtask_planner
from agents.subtask_planner.scheduler import sub_scheduler

from agents.simulator import simulator

from agents.cap_group_agents import ECS_manager
from agents.cap_group_agents import CES_manager
from agents.cap_group_agents import EVS_manager
from agents.cap_group_agents import IAM_service_manager
from agents.cap_group_agents import Huawei_Cloud_API_manager
from agents.cap_group_agents import VPC_network_manager

from LangGraph_test import repeater
from LangGraph_test import rander
from LangGraph_test import palindromist

from agency_swarm import set_openai_key
with open("~/keys/OPENAI_API_KEY.txt", 'r') as file:
    api_key = file.read()
set_openai_key(api_key)

leader = leader.create_agent()
task_planner = task_planner.create_agent()
inspector = inspector.create_agent()
scheduler = scheduler.create_agent()
capability_planner = capability_planner.create_agent()
inspector_capability = inspector_capability.create_agent()
subtask_planner = subtask_planner.create_agent()
sub_scheduler = sub_scheduler.create_agent()

repeater = repeater.create_agent()
rander = rander.create_agent()
palindromist = palindromist.create_agent()

simulator = simulator.create_agent()

ECS_manager = ECS_manager.create_agent()
CES_manager = CES_manager.create_agent()
EVS_manager = EVS_manager.create_agent()
IAM_service_manager = IAM_service_manager.create_agent()
Huawei_Cloud_API_manager = Huawei_Cloud_API_manager.create_agent()
VPC_network_manager = VPC_network_manager.create_agent()

chat_graph = [leader, 
              [leader, task_planner],
              [leader, inspector],
              [leader, subtask_planner],
              [leader, sub_scheduler],
              [leader, scheduler],
              [leader, ECS_manager],
              [leader, CES_manager],
              [leader, EVS_manager],
              [leader, IAM_service_manager],
              [leader, Huawei_Cloud_API_manager],
              [leader, VPC_network_manager],
              [leader, simulator],
              [leader, repeater],
              [leader, rander],
              [leader, palindromist]
            #   [leader, inspector_capability]
            #   [task_planner, capability_planner], 
              ]

agency_manifesto = """
"""

cap_group_agents = {
    "统一身份认证服务IAM能力群": IAM_service_manager,
    "华为云API处理能力群": Huawei_Cloud_API_manager,
    "弹性云服务器(ECS)管理能力群": ECS_manager,
    "VPC网络管理能力群": VPC_network_manager,
    "云硬盘EVS管理能力群": EVS_manager,
    "云监控CES能力群": CES_manager
}

agency = Agency(agency_chart=chat_graph, temperature=0.5, max_prompt_tokens=25000, )

plan_agents = {
    "task_planner": task_planner,
    "inspector": inspector,
    "scheduler": scheduler,
    "subtask_planner": subtask_planner,
    "sub_scheduler": sub_scheduler,
    "simulator": simulator
}

# agency.demo_gradio(height=700)
# agency.run_demo()
# agency.langgraph_test(repeater=repeater, rander=rander, palindromist=palindromist)
agency.task_planning(plan_agents=plan_agents, cap_group_agents=cap_group_agents)
# agency.create_ECS_simulation()