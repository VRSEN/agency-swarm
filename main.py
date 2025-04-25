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
from agents.cap_group_agents.CLUSTER_group import (
    CLUSTER_manager, CLUSTER_planner, CLUSTER_step_scheduler
)
from agents.cap_group_agents.NODE_group import (
    NODE_manager, NODE_planner, NODE_step_scheduler
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

from agents.cap_group_agents.CLUSTER_group.cap_agents.CLUSTER_lifecycle_agent import CLUSTER_lifecycle_agent
from agents.cap_group_agents.CLUSTER_group.cap_agents.CLUSTER_specification_change_agent import CLUSTER_specification_change_agent

from agents.cap_group_agents.NODE_group.cap_agents.NODE_lifecycle_agent import NODE_lifecycle_agent
from agents.cap_group_agents.NODE_group.cap_agents.NODE_pool_agent import NODE_pool_agent
from agents.cap_group_agents.NODE_group.cap_agents.NODE_scaling_protect_agent import NODE_scaling_protect_agent

from agents.basic_agents.api_agents import (
    API_param_selector, array_selector, param_selector, param_inspector, array_splitter
)
from agents.basic_agents.job_agent import check_log_agent
from agents.basic_agents.job_agent import job_agent
from agents.basic_agents.jobs_agent import jobs_agent
from agents.basic_agents.job_agent.tools.CheckLogForFailures import CheckLogForFailures
from agents.basic_agents.api_agents.tools.CheckParamRequired import CheckParamRequired
from agents.basic_agents.api_agents.tools.SelectAPIParam import SelectAPIParam
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable
from agents.basic_agents.api_agents.tools.SplitArray import SplitArray

from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))

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

CLUSTER_planner = CLUSTER_planner.create_agent()
CLUSTER_manager = CLUSTER_manager.create_agent()
CLUSTER_step_scheduler = CLUSTER_step_scheduler.create_agent()
CLUSTER_lifecycle_agent = CLUSTER_lifecycle_agent.create_agent()
CLUSTER_specification_change_agent = CLUSTER_specification_change_agent.create_agent()

NODE_planner = NODE_planner.create_agent()
NODE_manager = NODE_manager.create_agent()
NODE_step_scheduler = NODE_step_scheduler.create_agent()
NODE_lifecycle_agent = NODE_lifecycle_agent.create_agent()
NODE_pool_agent = NODE_pool_agent.create_agent()
NODE_scaling_protect_agent = NODE_scaling_protect_agent.create_agent()

API_param_selector = API_param_selector.create_agent()
array_selector = array_selector.create_agent()
array_splitter = array_splitter.create_agent()
param_selector = param_selector.create_agent()
param_inspector = param_inspector.create_agent()
check_log_agent = check_log_agent.create_agent()
job_agent = job_agent.create_agent()
jobs_agent = jobs_agent.create_agent()

chat_graph = [task_planner, scheduler, inspector,
              subtask_planner, subtask_manager, subtask_scheduler, subtask_inspector,
              step_inspector,
              basic_cap_solver, param_asker,
              array_splitter,
              param_inspector,

              check_log_agent,
            #   CES_planner, CES_step_scheduler,
              ECS_planner, ECS_step_scheduler,
            #   EVS_planner, EVS_step_scheduler,
            #   Huawei_Cloud_API_planner, Huawei_Cloud_API_step_scheduler,
            #   IAM_service_planner, IAM_service_step_scheduler,
              IMS_planner, IMS_step_scheduler,
            #   OS_planner, OS_step_scheduler,
              VPC_network_planner, VPC_network_step_scheduler,
              CLUSTER_planner, CLUSTER_step_scheduler,
              NODE_planner, NODE_step_scheduler,

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
            #   [ECS_recommend_agent, job_agent],
            #   [ECS_specification_query_agent,job_agent],

              
              [ECS_specification_query_agent, ECS_manager],
              [ECS_recommend_agent, ECS_manager],
              [ECS_netcard_agent, ECS_manager],
              [ECS_instance_agent, ECS_manager],
              [ECS_harddisk_agent, ECS_manager],

            #   [EVS_manager, EVS_clouddiskt_agent],
            #   [EVS_manager, EVS_snapshot_agent],

            #   [IAM_service_manager, AKSK_agent],

              [IMS_manager, IMS_agent],
            #   [IMS_agent, job_agent],
              [IMS_agent, IMS_manager],

            #   [OS_manager, OS_agent],


              [VPC_network_manager, VPC_secgroup_agent],
              [VPC_network_manager, VPC_subnet_agent],
              [VPC_network_manager, VPC_vpc_agent],

            #   [VPC_secgroup_agent, job_agent],
            #   [VPC_subnet_agent, job_agent],
            #   [VPC_vpc_agent, job_agent],


              [VPC_vpc_agent, VPC_network_manager],
              [VPC_subnet_agent, VPC_network_manager],
              [VPC_secgroup_agent, VPC_network_manager],

              [CLUSTER_manager, CLUSTER_lifecycle_agent],
              [CLUSTER_manager, CLUSTER_specification_change_agent],

            #   [CLUSTER_lifecycle_agent, job_agent],
            #   [CLUSTER_specification_change_agent, job_agent],

              [CLUSTER_lifecycle_agent, CLUSTER_manager],
              [CLUSTER_specification_change_agent, CLUSTER_manager],

              [NODE_manager, NODE_lifecycle_agent],
              [NODE_manager, NODE_pool_agent],
              [NODE_manager, NODE_scaling_protect_agent],

            #   [NODE_lifecycle_agent, job_agent],
            #   [NODE_pool_agent, job_agent],
            #   [NODE_scaling_protect_agent, job_agent],
              
              [NODE_lifecycle_agent, NODE_manager],
              [NODE_pool_agent, NODE_manager],
              [NODE_scaling_protect_agent, NODE_manager],

              
              [ECS_harddisk_agent, API_param_selector],
              [ECS_instance_agent, API_param_selector],
              [ECS_netcard_agent, API_param_selector],
              [ECS_recommend_agent, API_param_selector],
              [ECS_specification_query_agent, API_param_selector],
              [IMS_agent, API_param_selector],
              [VPC_secgroup_agent, API_param_selector],
              [VPC_subnet_agent, API_param_selector],
              [VPC_vpc_agent, API_param_selector],
              [CLUSTER_lifecycle_agent, API_param_selector],
              [CLUSTER_specification_change_agent, API_param_selector],
              [NODE_lifecycle_agent, API_param_selector],
              [NODE_pool_agent, API_param_selector],
              [NODE_scaling_protect_agent, API_param_selector],

            #   [job_agent, API_filler],
            #   [jobs_agent, API_filler],

              [param_selector, array_selector],
              [array_splitter],
              [AKSK_agent],

              # [ECS_manager, param_asker],
              # [IMS_manager, param_asker],
              # [VPC_network_manager, param_asker],
              # [CLUSTER_manager, param_asker],
              # [NODE_manager, param_asker],

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
        (CheckParamRequired, array_selector),
        (CheckLogForFailures, check_log_agent),
        (SplitArray, array_splitter)
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
    "集群管理能力群": [CLUSTER_planner, CLUSTER_manager, CLUSTER_step_scheduler],
    "节点管理能力群": [NODE_planner, NODE_manager, NODE_step_scheduler],
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
    "集群管理能力群": [CLUSTER_lifecycle_agent, CLUSTER_specification_change_agent],
    "节点管理能力群": [NODE_lifecycle_agent, NODE_pool_agent, NODE_scaling_protect_agent],
}

step_json = {
    "title": "创建节点",
    "id": "step_1",
    "agent": ["NODE_lifecycle_agent"],
    "description": "在cn-north-4a可用区中，名为ccetest的CCE集群中创建一个节点，节点名字为node-1，集群id为eeb8f029-1c4b-11f0-a423-0255ac100260，节点规格为c6.large.2，系统盘和数据盘大小分别为50GB和100GB，磁盘类型都为SSD，节点通过密码方式登录，用户名为'root', 密码为'JDYkc2FsdCR1SzEzUEgvMy9rOHZRQ0UzRFBEVzFiZm1UMmVZSnFEQjMydzFxOVY5WUt3M2ZmR0JTZWN1N2ZNZlkzYmY5Z2ZDNlJlTHp6NGl3anc3WHM5RDFUcmNuLg=='",
    "dep": []
}

perpared = {
    "cap_group": "节点管理能力群",
    "step": step_json
}

text = "在cn-north-4a可用区中，名为ccetest的CCE集群中加入一个节点，节点名字为node-1，集群id为eeb8f029-1c4b-11f0-a423-0255ac100260，节点规格为c6.large.2，系统盘和数据盘大小分别为50GB和100GB，磁盘类型都为SSD"
# text = "在cn-north-4a可用区创建一个名为ccetest的CCE集群，最小规格；未创建vpc和子网，需要创建名为vpc111的vpc和名为subnet111的子网，vpc的cidr为192.168.0.0/24，网关ip为192.168.0.1; 之后你需要在该CCE集群中加入三个节点"
# text = "在北京cn-north-4a可用区创建一个最低规格的CCE，名为'ccetest'，已有vpc和子网，VPC id为8bf558f4-2f96-4248-9cb0-fee7a2a6cebb，子网id为0519a325-6fa3-4f68-83ec-6f13263167d2"
# text = "创建一个8核32g的ECS，操作系统选择为Ubuntu 20.04。"
# text = "在北京可用区创建三个ecs，之后删除创建时间超过5分钟的ecs"
# text = "在华为云ecs上部署mysql和postgresql，并用sysbench测试它们的性能"
# text = input("👤 USER: ")

# agency.test_single_cap_agent(plan_agents=plan_agents, cap_group_agents=cap_group_agents, cap_agents=cap_agents, **perpared)

# agency.langgraph_test(repeater=repeater, rander=rander, palindromist=palindromist)
agency.task_planning(original_request=text, plan_agents=plan_agents, cap_group_agents=cap_group_agents, cap_agents=cap_agents)
