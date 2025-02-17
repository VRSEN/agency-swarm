from agency_swarm import Agent, Agency

from agents.task_planner import (
    task_planner, scheduler, inspector
)
from agents.subtask_planner import (
    subtask_planner, subtask_manager, subtask_scheduler, subtask_inspector
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
from agents.cap_group_agents.IMS_group import (
    IMS_manager, IMS_planner, IMS_step_scheduler
)
from agents.cap_group_agents.OS_group import (
    OS_manager, OS_planner, OS_step_scheduler
)
from agents.cap_group_agents.VPC_network import (
    VPC_network_manager, VPC_network_planner, VPC_network_step_scheduler
)
from agents.cap_group_agents import step_inspector

from agents.cap_group_agents import (
    basic_cap_solver, param_asker
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

from agents.cap_group_agents.IMS_group.cap_agents.IMS_agent import IMS_agent

from agents.cap_group_agents.OS_group.cap_agents.OS_agent import OS_agent

from agents.cap_group_agents.VPC_network.cap_agents.VPC_secgroup_agent import VPC_secgroup_agent
from agents.cap_group_agents.VPC_network.cap_agents.VPC_subnet_agent import VPC_subnet_agent
from agents.cap_group_agents.VPC_network.cap_agents.VPC_vpc_agent import VPC_vpc_agent

from agents.basic_agents.api_agents import (
    API_caller, API_filler, API_param_selector, array_filler, array_selector, param_filler, param_selector
)
from agents.basic_agents.job_agent import job_agent
from agents.basic_agents.jobs_agent import jobs_agent
from agents.basic_agents.api_agents.tools.SelectAPIParam import SelectAPIParam
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable
from agents.basic_agents.api_agents.tools.FillAPI import FillAPI
from agents.basic_agents.api_agents.tools.FillParamTable import FillParamTable

from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))
user_request = os.getenv('USER_REQUEST')

task_planner = task_planner.create_agent()
scheduler = scheduler.create_agent()
inspector = inspector.create_agent()

subtask_planner = subtask_planner.create_agent()
subtask_manager = subtask_manager.create_agent()
subtask_scheduler = subtask_scheduler.create_agent()
subtask_inspector = subtask_inspector.create_agent()

step_inspector = step_inspector.create_agent()

basic_cap_solver = basic_cap_solver.create_agent()
param_asker = param_asker.create_agent()

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

# IAM_service_planner = IAM_service_planner.create_agent()
# IAM_service_manager = IAM_service_manager.create_agent()
# IAM_service_step_scheduler = IAM_service_step_scheduler.create_agent()
AKSK_agent = AKSK_agent.create_agent()

IMS_planner = IMS_planner.create_agent()
IMS_manager = IMS_manager.create_agent()
IMS_step_scheduler = IMS_step_scheduler.create_agent()
IMS_agent = IMS_agent.create_agent()

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
job_agent = job_agent.create_agent()
jobs_agent = jobs_agent.create_agent()

chat_graph = [task_planner, scheduler, inspector,
              subtask_planner, subtask_manager, subtask_scheduler, subtask_inspector,
              step_inspector,
              basic_cap_solver, param_asker,
            #   CES_planner, CES_step_scheduler,
              ECS_planner, ECS_step_scheduler,
            #   EVS_planner, EVS_step_scheduler,
            #   Huawei_Cloud_API_planner, Huawei_Cloud_API_step_scheduler,
            #   IAM_service_planner, IAM_service_step_scheduler,
              IMS_planner, IMS_step_scheduler,
            #   OS_planner, OS_step_scheduler,
              VPC_network_planner, VPC_network_step_scheduler,

            #   [subtask_manager, CES_manager],
              # [subtask_manager, ECS_manager],
            #   [subtask_manager, EVS_manager],
              # [subtask_manager, IMS_manager],
            #   [subtask_manager, OS_manager],
              # [subtask_manager, VPC_network_manager],

              # [ECS_manager, subtask_manager],
              # [IMS_manager, subtask_manager],
              # [VPC_network_manager, subtask_manager],

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

              [ECS_harddisk_agent, jobs_agent],
              [ECS_instance_agent, jobs_agent],
              [ECS_netcard_agent, jobs_agent],
              [ECS_recommend_agent, job_agent],
              [ECS_specification_query_agent,job_agent],

              
              [ECS_specification_query_agent, ECS_manager],
              [ECS_recommend_agent, ECS_manager],
              [ECS_netcard_agent, ECS_manager],
              [ECS_instance_agent, ECS_manager],
              [ECS_harddisk_agent, ECS_manager],

            #   [EVS_manager, EVS_clouddiskt_agent],
            #   [EVS_manager, EVS_snapshot_agent],

            #   [IAM_service_manager, AKSK_agent],

              [IMS_manager, IMS_agent],
              [IMS_agent, job_agent],
              [IMS_agent, IMS_manager],

            #   [OS_manager, OS_agent],


              [VPC_network_manager, VPC_secgroup_agent],
              [VPC_network_manager, VPC_subnet_agent],
              [VPC_network_manager, VPC_vpc_agent],

              [VPC_secgroup_agent, job_agent],
              [VPC_subnet_agent, job_agent],
              [VPC_vpc_agent, job_agent],


              [VPC_vpc_agent, VPC_network_manager],
              [VPC_subnet_agent, VPC_network_manager],
              [VPC_secgroup_agent, VPC_network_manager],

              
              [ECS_harddisk_agent, API_param_selector],
              [ECS_instance_agent, API_param_selector],
              [ECS_netcard_agent, API_param_selector],
              [ECS_recommend_agent, API_param_selector],
              [ECS_specification_query_agent, API_param_selector],
              [IMS_agent, API_param_selector],
              [VPC_secgroup_agent, API_param_selector],
              [VPC_subnet_agent, API_param_selector],
              [VPC_vpc_agent, API_param_selector],
              [job_agent, API_filler],
              [jobs_agent, API_filler],

              [param_selector, array_selector],
              [API_filler, API_caller, AKSK_agent],
              [param_filler, array_filler],
              [array_filler, param_filler],

              [ECS_manager, param_asker],
              [IMS_manager, param_asker],
              [VPC_network_manager, param_asker],

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
    "inspector": inspector,
    "scheduler": scheduler,
    "subtask_planner": subtask_planner,
    "subtask_scheduler": subtask_scheduler,
    "subtask_inspector": subtask_inspector,
    "step_inspector": step_inspector
    # "simulator": simulator
}

cap_group_agents = {
    # "云监控CES能力群": [CES_planner, CES_manager, CES_step_scheduler], 
    "弹性云服务器(ECS)管理能力群": [ECS_planner, ECS_manager, ECS_step_scheduler],
    # "云硬盘EVS管理能力群": [EVS_planner, EVS_manager, EVS_step_scheduler],
    # "华为云API处理能力群": [Huawei_Cloud_API_planner, Huawei_Cloud_API_manager, Huawei_Cloud_API_step_scheduler],
    # "统一身份认证服务IAM能力群": [IAM_service_planner, IAM_service_manager, IAM_service_step_scheduler],
    "镜像管理能力群": [IMS_planner, IMS_manager, IMS_step_scheduler],
    # "操作系统管理能力群": [OS_planner, OS_manager, OS_step_scheduler],
    "VPC网络管理能力群": [VPC_network_planner, VPC_network_manager, VPC_network_step_scheduler],
    # "华为云元信息管理能力群": [Huawei_meta_info_planner, ]
    "简单任务处理能力群": [basic_cap_solver],
}

cap_agents = {
    # "云监控CES能力群": [CES_alarm_history_agent, CES_alarm_rule_agent, CES_dashboard_agent, CES_data_agent, CES_metric_agent, CES_event_agent],
    "弹性云服务器(ECS)管理能力群": [ECS_harddisk_agent, ECS_instance_agent, ECS_netcard_agent, ECS_recommend_agent, ECS_specification_query_agent],
    # "云硬盘EVS管理能力群": [EVS_clouddiskt_agent, EVS_snapshot_agent],
    # "华为云API处理能力群": [],
    # "统一身份认证服务IAM能力群": [AKSK_agent],
    "镜像管理能力群": [IMS_agent],
    # "操作系统管理能力群": [OS_agent],
    "VPC网络管理能力群": [VPC_secgroup_agent, VPC_subnet_agent, VPC_vpc_agent],
}

# agency.langgraph_test(repeater=repeater, rander=rander, palindromist=palindromist)
agency.task_planning(plan_agents=plan_agents, cap_group_agents=cap_group_agents, cap_agents=cap_agents, user_request=user_request)
