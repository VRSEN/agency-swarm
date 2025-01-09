from agency_swarm import Agent, Agency

from agents.task_planner import (
    task_planner, scheduler, inspector
)
from agents.subtask_planner import (
    subtask_planner, sub_scheduler
)
from agents.cap_group_agents.CES_group import (
    CES_manager, CES_planner, CES_step_scheduler
)
from agents.cap_group_agents.ECS_group import (
    ECS_manager, ECS_planner, ECS_step_scheduler
)
from agents.cap_group_agents.EVS_group import (
    EVS_manager, EVS_planner, EVS_step_scheduler
)
from agents.cap_group_agents.Huawei_Cloud_API_group import (
    Huawei_Cloud_API_manager, Huawei_Cloud_API_planner, Huawei_Cloud_API_step_scheduler
)
from agents.cap_group_agents.IAM_service_group import (
    IAM_service_manager, IAM_service_planner, IAM_service_step_scheduler
)
from agents.cap_group_agents.OS_group import (
    OS_manager, OS_planner, OS_step_scheduler
)
from agents.cap_group_agents.VPC_network import (
    VPC_network_manager, VPC_network_planner, VPC_network_step_scheduler
)
from agents.cap_group_agents.CES_group.cap_agents.CES_alarm_history_agent import CES_alarm_history_agent
from agents.cap_group_agents.CES_group.cap_agents.CES_alarm_rule_agent import CES_alarm_rule_agent
from agents.cap_group_agents.CES_group.cap_agents.CES_dashboard_agent import CES_dashboard_agent
from agents.cap_group_agents.CES_group.cap_agents.CES_data_agent import CES_data_agent
from agents.cap_group_agents.CES_group.cap_agents.CES_event_agent import CES_event_agent
from agents.cap_group_agents.CES_group.cap_agents.CES_metric_agent import CES_metric_agent

from agents.cap_group_agents.ECS_group.cap_agents.ECS_harddisk_agent import ECS_harddisk_agent
from agents.cap_group_agents.ECS_group.cap_agents.ECS_instance_agent import ECS_instance_agent
from agents.cap_group_agents.ECS_group.cap_agents.ECS_netcard_agent import ECS_netcard_agent
from agents.cap_group_agents.ECS_group.cap_agents.ECS_recommend_agent import ECS_recommend_agent
from agents.cap_group_agents.ECS_group.cap_agents.ECS_specification_query_agent import ECS_specification_query_agent

from agents.cap_group_agents.EVS_group.cap_agents.EVS_clouddiskt_agent import EVS_clouddiskt_agent
from agents.cap_group_agents.EVS_group.cap_agents.EVS_snapshot_agent import EVS_snapshot_agent

from agents.cap_group_agents.IAM_service_group.cap_agents.AKSK_agent import AKSK_agent

from agents.cap_group_agents.OS_group.cap_agents.OS_agent import OS_agent

from agents.cap_group_agents.VPC_network.cap_agents.VPC_secgroup_agent import VPC_secgroup_agent
from agents.cap_group_agents.VPC_network.cap_agents.VPC_subnet_agent import VPC_subnet_agent
from agents.cap_group_agents.VPC_network.cap_agents.VPC_vpc_agent import VPC_vpc_agent

from agents.base_agents import (
    API_caller, API_filler, API_param_selector, array_filler, array_selector, param_filler, param_selector
)
from agents.base_agents.tools.SelectAPIParam import SelectAPIParam
from agents.base_agents.tools.SelectParamTable import SelectParamTable
from agents.base_agents.tools.FillAPI import FillAPI
from agents.base_agents.tools.FillParamTable import FillParamTable

from agency_swarm import set_openai_key
with open("/root/keys/OEPNAI_API_KEY.txt", 'r') as file:
    api_key = file.read()

set_openai_key(api_key)

task_planner = task_planner.create_agent()
# inspector = inspector.create_agent()
scheduler = scheduler.create_agent()
subtask_planner = subtask_planner.create_agent()
sub_scheduler = sub_scheduler.create_agent()

# repeater = repeater.create_agent()
# rander = rander.create_agent()
# palindromist = palindromist.create_agent()

# simulator = simulator.create_agent()

# CES_planner = CES_planner.create_agent()
# CES_manager = CES_manager.create_agent()
# CES_step_scheduler = CES_step_scheduler.create_agent()
# CES_alarm_history_agent = CES_alarm_history_agent.create_agent()
# CES_alarm_rule_agent = CES_alarm_rule_agent.create_agent()
# CES_dashboard_agent = CES_dashboard_agent.create_agent()
# CES_data_agent = CES_data_agent.create_agent()
# CES_event_agent = CES_event_agent.create_agent()
# CES_metric_agent = CES_metric_agent.create_agent()

ECS_planner = ECS_planner.create_agent()
ECS_manager = ECS_manager.create_agent()
ECS_step_scheduler = ECS_step_scheduler.create_agent()
ECS_harddisk_agent = ECS_harddisk_agent.create_agent()
ECS_instance_agent = ECS_instance_agent.create_agent()
ECS_netcard_agent = ECS_netcard_agent.create_agent()
ECS_recommend_agent = ECS_recommend_agent.create_agent()
ECS_specification_query_agent = ECS_specification_query_agent.create_agent()

# EVS_planner = EVS_planner.create_agent()
# EVS_manager = EVS_manager.create_agent()
# EVS_step_scheduler = EVS_step_scheduler.create_agent()
# EVS_clouddiskt_agent = EVS_clouddiskt_agent.create_agent()
# EVS_snapshot_agent = EVS_snapshot_agent.create_agent()

IAM_service_planner = IAM_service_planner.create_agent()
IAM_service_manager = IAM_service_manager.create_agent()
IAM_service_step_scheduler = IAM_service_step_scheduler.create_agent()
AKSK_agent = AKSK_agent.create_agent()

# Huawei_Cloud_API_planner = Huawei_Cloud_API_planner.create_agent()
# Huawei_Cloud_API_manager = Huawei_Cloud_API_manager.create_agent()
# Huawei_Cloud_API_step_scheduler = Huawei_Cloud_API_step_scheduler.create_agent()

# OS_planner = OS_planner.create_agent()
# OS_manager = OS_manager.create_agent()
# OS_step_scheduler = OS_step_scheduler.create_agent()
# OS_agent = OS_agent.create_agent()

VPC_network_planner = VPC_network_planner.create_agent()
VPC_network_manager = VPC_network_manager.create_agent()
VPC_network_step_scheduler = VPC_network_step_scheduler.create_agent()
VPC_secgroup_agent = VPC_secgroup_agent.create_agent()
VPC_subnet_agent = VPC_subnet_agent.create_agent()
VPC_vpc_agent = VPC_vpc_agent.create_agent()

API_caller = API_caller.create_agent()
API_filler = API_filler.create_agent()
API_param_selector = API_param_selector.create_agent()
array_filler = array_filler.create_agent()
array_selector = array_selector.create_agent()
param_filler = param_filler.create_agent()
param_selector = param_selector.create_agent()

chat_graph = [task_planner, scheduler,
              subtask_planner, sub_scheduler,
            #   CES_planner, CES_step_scheduler,
              ECS_planner, ECS_step_scheduler,
            #   EVS_planner, EVS_step_scheduler,
            #   Huawei_Cloud_API_planner, Huawei_Cloud_API_step_scheduler,
              IAM_service_planner, IAM_service_step_scheduler,
            #   OS_planner, OS_step_scheduler,
              VPC_network_planner, VPC_network_step_scheduler,

            #   [CES_manager, CES_alarm_history_agent],
            #   [CES_manager, CES_alarm_rule_agent],
            #   [CES_manager, CES_dashboard_agent],
            #   [CES_manager, CES_data_agent],
            #   [CES_manager, CES_metric_agent],
            #   [CES_manager, CES_event_agent],

              [ECS_manager, ECS_harddisk_agent],
              [ECS_manager, ECS_instance_agent],
              [ECS_manager, ECS_netcard_agent],
              [ECS_manager, ECS_recommend_agent],
              [ECS_manager, ECS_specification_query_agent],

            #   [EVS_manager, EVS_clouddiskt_agent],
            #   [EVS_manager, EVS_snapshot_agent],

              [IAM_service_manager, AKSK_agent],

            #   [OS_manager, OS_agent],


              [VPC_network_manager, VPC_secgroup_agent],
              [VPC_network_manager, VPC_subnet_agent],
              [VPC_network_manager, VPC_vpc_agent],
              
              [ECS_harddisk_agent, API_param_selector],
              [ECS_harddisk_agent, API_filler],
              [ECS_instance_agent, API_param_selector],
              [ECS_instance_agent, API_filler],
              [ECS_netcard_agent, API_param_selector],
              [ECS_netcard_agent, API_filler],
              [ECS_recommend_agent, API_param_selector],
              [ECS_recommend_agent, API_filler],
              [ECS_specification_query_agent, API_param_selector],
              [ECS_specification_query_agent, API_filler],
              [VPC_secgroup_agent, API_param_selector],
              [VPC_secgroup_agent, API_filler],
              [VPC_subnet_agent, API_param_selector],
              [VPC_subnet_agent, API_filler],
              [VPC_vpc_agent, API_param_selector],
              [VPC_vpc_agent, API_filler],

              [param_selector, array_selector],
              [API_filler, API_caller, AKSK_agent],
              [param_filler, array_filler],
              [array_filler, param_filler],

              # [leader, simulator],
              # [leader, repeater],
              # [leader, rander],
              # [leader, palindromist]
              ]

agency_manifesto = """
"""

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

agency = Agency(agency_chart=chat_graph,
                thread_strategy=thread_strategy,
                temperature=0.5,
                max_prompt_tokens=25000,)

plan_agents = {
    "task_planner": task_planner,
    # "inspector": inspector,
    "scheduler": scheduler,
    "subtask_planner": subtask_planner,
    "sub_scheduler": sub_scheduler,
    # "simulator": simulator
}

cap_group_agents = {
    "统一身份认证服务IAM能力群": [IAM_service_planner, IAM_service_manager, IAM_service_step_scheduler], 
    # "华为云API处理能力群": [Huawei_Cloud_API_planner, Huawei_Cloud_API_manager, Huawei_Cloud_API_step_scheduler],
    "弹性云服务器(ECS)管理能力群": [ECS_planner, ECS_manager, ECS_step_scheduler],
    "VPC网络管理能力群": [VPC_network_planner, VPC_network_manager, VPC_network_step_scheduler],
    # "云硬盘EVS管理能力群": [EVS_planner, EVS_manager, EVS_step_scheduler],
    # "云监控CES能力群": [CES_planner, CES_manager, CES_step_scheduler],
    # "操作系统管理能力群": [OS_planner, OS_manager, OS_step_scheduler],
}

cap_agents = {
    "统一身份认证服务IAM能力群": [AKSK_agent],
    # "华为云API处理能力群": [],
    "弹性云服务器(ECS)管理能力群": [ECS_harddisk_agent, ECS_instance_agent, ECS_netcard_agent, ECS_recommend_agent, ECS_specification_query_agent],
    "VPC网络管理能力群": [VPC_secgroup_agent, VPC_subnet_agent, VPC_vpc_agent],
    # "云硬盘EVS管理能力群": [EVS_clouddiskt_agent, EVS_snapshot_agent],
    # "云监控CES能力群": [CES_alarm_history_agent, CES_alarm_rule_agent, CES_dashboard_agent, CES_data_agent, CES_metric_agent, CES_event_agent],
    # "操作系统管理能力群": [OS_agent],
}

# agency.langgraph_test(repeater=repeater, rander=rander, palindromist=palindromist)
agency.task_planning(plan_agents=plan_agents, cap_group_agents=cap_group_agents, cap_agents=cap_agents)
