from agency_swarm import Agent, Agency

from agents import leader
from agents.task_planner import (
    task_planner, scheduler, inspector
)
from agents.subtask_planner import (
    subtask_planner, sub_scheduler
)
from agents.cap_group_agents.CES_group import CES_manager
from agents.cap_group_agents.ECS_group import ECS_manager
from agents.cap_group_agents.EVS_group import EVS_manager
from agents.cap_group_agents.Huawei_Cloud_API_group import Huawei_Cloud_API_manager
from agents.cap_group_agents.IAM_service_group import IAM_service_manager
from agents.cap_group_agents.VPC_network import VPC_network_manager

from agency_swarm import set_openai_key
with open("/root/keys/OEPNAI_API_KEY.txt", 'r') as file:
    api_key = file.read()

set_openai_key(api_key)

leader = leader.create_agent()
task_planner = task_planner.create_agent()
inspector = inspector.create_agent()
scheduler = scheduler.create_agent()
subtask_planner = subtask_planner.create_agent()
sub_scheduler = sub_scheduler.create_agent()

# repeater = repeater.create_agent()
# rander = rander.create_agent()
# palindromist = palindromist.create_agent()

# simulator = simulator.create_agent()

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
              # [leader, simulator],
              # [leader, repeater],
              # [leader, rander],
              # [leader, palindromist]
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
    # "simulator": simulator
}

# agency.langgraph_test(repeater=repeater, rander=rander, palindromist=palindromist)
agency.task_planning(plan_agents=plan_agents, cap_group_agents=cap_group_agents)
