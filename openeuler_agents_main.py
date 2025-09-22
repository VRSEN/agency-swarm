import datetime
import os
import sys

from dotenv import load_dotenv

from agency_swarm import Agency, Agent, set_openai_key
from agents.openeuler_agents import (
    check_log_agent,
    os_rag_optimizer,
    security_rag_optimizer,
    software_rag_optimizer,
    step_inspector,
)
from agents.openeuler_agents.os_group import (
    os_planner, 
    os_step_scheduler,
)
from agents.openeuler_agents.os_group.network_agent import network_agent
from agents.openeuler_agents.os_group.permissions_agent import permissions_agent
from agents.openeuler_agents.os_group.basic_agent import basic_agent
from agents.openeuler_agents.os_group.user_agent import user_agent
from agents.openeuler_agents.security_group import (
    security_planner,
    security_step_scheduler,
)
from agents.openeuler_agents.security_group.secscanner_agent import secscanner_agent
from agents.openeuler_agents.security_group.syscare_agent import syscare_agent
from agents.openeuler_agents.software_group import (
    software_planner,
    software_step_scheduler,
)
from agents.openeuler_agents.software_group.atune_agent import atune_agent
from agents.openeuler_agents.software_group.package_agent import package_agent
from agents.openeuler_agents.software_group.repository_agent import repository_agent
from agents.openeuler_agents.subtask_planner import (
    subtask_inspector,
    subtask_planner,
    subtask_scheduler,
)
from agents.openeuler_agents.task_planner import (
    task_inspector,
    task_inspector_rag,
    task_planner,
    task_planner_rag,
    task_scheduler,
    task_scheduler_rag,
)

from agents.subtask_planner import(
    subtask_manager
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

from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand

from agents.openeuler_agents.comprehensive_group import (
comprehensive_planner, comprehensive_step_scheduler
)
from agents.openeuler_agents.comprehensive_group.text_agent import text_agent
load_dotenv()
set_openai_key(os.getenv("OPENAI_API_KEY"))


def main():
    # 添加日志功能：创建一个日志文件，用当前时间作为文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join("log", f"run_log_{timestamp}.txt")

    # 创建日志文件
    log_file = open(log_file_path, "w", encoding="utf-8", buffering=1)

    # 创建自定义的输出类，同时将输出发送到文件和终端
    class TeeOutput:
        def __init__(self, file, terminal):
            self.file = file
            self.terminal = terminal

        def write(self, message):
            self.terminal.write(message)
            self.file.write(message)

        def flush(self):
            self.terminal.flush()
            self.file.flush()

    # 保存原始的stdout，并设置新的输出重定向
    original_stdout = sys.stdout
    sys.stdout = TeeOutput(log_file, original_stdout)

    use_rag = os.getenv("USE_RAG")

    try:
        # 以下是日志功能更新前的代码
        task_planner_instance = task_planner.create_agent()
        task_scheduler_instance = task_scheduler.create_agent()
        task_inspector_instance = task_inspector.create_agent()

        task_planner_rag_instance = task_planner_rag.create_agent()
        task_scheduler_rag_instance = task_scheduler_rag.create_agent()
        task_inspector_rag_instance = task_inspector_rag.create_agent()

        software_rag_optimizer_instance = software_rag_optimizer.create_agent()
        security_rag_optimizer_instance = security_rag_optimizer.create_agent()
        os_rag_optimizer_instance = os_rag_optimizer.create_agent()

        subtask_planner_instance = subtask_planner.create_agent()
        subtask_scheduler_instance = subtask_scheduler.create_agent()
        subtask_inspector_instance = subtask_inspector.create_agent()
        subtask_manager_instance = subtask_manager.create_agent()

        step_inspector_instance = step_inspector.create_agent()

        software_planner_instance = software_planner.create_agent()
        software_step_scheduler_instance = software_step_scheduler.create_agent()
        package_agent_instance = package_agent.create_agent()
        repository_agent_instance = repository_agent.create_agent()
        atune_agent_instance = atune_agent.create_agent()

        security_planner_instance = security_planner.create_agent()
        security_step_scheduler_instance = security_step_scheduler.create_agent()
        secscanner_agent_instance = secscanner_agent.create_agent()
        syscare_agent_instance = syscare_agent.create_agent()

        os_planner_instance = os_planner.create_agent()
        os_step_scheduler_instance = os_step_scheduler.create_agent()
        permissions_agent_instance = permissions_agent.create_agent()
        network_agent_instance = network_agent.create_agent()
        user_agent_instance = user_agent.create_agent()
        basic_agent_instance = basic_agent.create_agent()

        check_log_agent_instance = check_log_agent.create_agent()

        basic_cap_solver_instance = basic_cap_solver.create_agent()
        param_asker_instance = param_asker.create_agent()

        comprehensive_planner_instance = comprehensive_planner.create_agent()
        comprehensive_step_scheduler_instance = comprehensive_step_scheduler.create_agent()
        text_agent_instance = text_agent.create_agent()

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

        ECS_planner_instance = ECS_planner.create_agent()
        ECS_manager_instance = ECS_manager.create_agent()
        ECS_step_scheduler_instance = ECS_step_scheduler.create_agent()
        ECS_harddisk_agent_instance = ECS_harddisk_agent.create_agent()
        ECS_instance_agent_instance = ECS_instance_agent.create_agent()
        ECS_netcard_agent_instance = ECS_netcard_agent.create_agent()
        ECS_recommend_agent_instance = ECS_recommend_agent.create_agent()
        ECS_specification_query_agent_instance = ECS_specification_query_agent.create_agent()

        # EVS_planner = EVS_planner.create_agent()
        # EVS_manager = EVS_manager.create_agent()
        # EVS_step_scheduler = EVS_step_scheduler.create_agent()
        # EVS_clouddiskt_agent = EVS_clouddiskt_agent.create_agent()
        # EVS_snapshot_agent = EVS_snapshot_agent.create_agent()

        # IAM_service_planner = IAM_service_planner.create_agent()
        # IAM_service_manager = IAM_service_manager.create_agent()
        # IAM_service_step_scheduler = IAM_service_step_scheduler.create_agent()
        AKSK_agent_instance = AKSK_agent.create_agent()

        IMS_planner_instance = IMS_planner.create_agent()
        IMS_manager_instance = IMS_manager.create_agent()
        IMS_step_scheduler_instance = IMS_step_scheduler.create_agent()
        IMS_agent_instance = IMS_agent.create_agent()

        # Huawei_Cloud_API_planner = Huawei_Cloud_API_planner.create_agent()
        # Huawei_Cloud_API_manager = Huawei_Cloud_API_manager.create_agent()
        # Huawei_Cloud_API_step_scheduler = Huawei_Cloud_API_step_scheduler.create_agent()

        # OS_planner = OS_planner.create_agent()
        # OS_manager = OS_manager.create_agent()
        # OS_step_scheduler = OS_step_scheduler.create_agent()
        # OS_agent = OS_agent.create_agent()

        VPC_network_planner_instance = VPC_network_planner.create_agent()
        VPC_network_manager_instance = VPC_network_manager.create_agent()
        VPC_network_step_scheduler_instance = VPC_network_step_scheduler.create_agent()
        VPC_secgroup_agent_instance = VPC_secgroup_agent.create_agent()
        VPC_subnet_agent_instance = VPC_subnet_agent.create_agent()
        VPC_vpc_agent_instance = VPC_vpc_agent.create_agent()

        CLUSTER_planner_instance = CLUSTER_planner.create_agent()
        CLUSTER_manager_instance = CLUSTER_manager.create_agent()
        CLUSTER_step_scheduler_instance = CLUSTER_step_scheduler.create_agent()
        CLUSTER_lifecycle_agent_instance = CLUSTER_lifecycle_agent.create_agent()
        CLUSTER_specification_change_agent_instance = CLUSTER_specification_change_agent.create_agent()

        NODE_planner_instance = NODE_planner.create_agent()
        NODE_manager_instance = NODE_manager.create_agent()
        NODE_step_scheduler_instance = NODE_step_scheduler.create_agent()
        NODE_lifecycle_agent_instance = NODE_lifecycle_agent.create_agent()
        NODE_pool_agent_instance = NODE_pool_agent.create_agent()
        NODE_scaling_protect_agent_instance = NODE_scaling_protect_agent.create_agent()

        API_param_selector_instance = API_param_selector.create_agent()
        array_selector_instance = array_selector.create_agent()
        array_splitter_instance = array_splitter.create_agent()
        param_selector_instance = param_selector.create_agent()
        param_inspector_instance = param_inspector.create_agent()
#        check_log_agent_instance = check_log_agent.create_agent()
        job_agent_instance = job_agent.create_agent()
        jobs_agent_instance = jobs_agent.create_agent()

        
        
        chat_graph = [
            # task
            task_planner_instance,
            task_scheduler_instance,
            task_inspector_instance,
            # task rag
            task_planner_rag_instance,
            task_scheduler_rag_instance,
            task_inspector_rag_instance,
            # task optimize rag
            software_rag_optimizer_instance,
            security_rag_optimizer_instance,
            os_rag_optimizer_instance,
            # subtask
            subtask_planner_instance,
            subtask_scheduler_instance,
            subtask_inspector_instance,
            subtask_manager_instance,
            # step
            step_inspector_instance,
            # check log
            check_log_agent_instance,
            # 每个能力群的planner和step scheduler
            software_planner_instance,
            software_step_scheduler_instance,
            security_planner_instance,
            security_step_scheduler_instance,
            os_planner_instance,
            os_step_scheduler_instance,
            # 软件能力 agent
            package_agent_instance,
            repository_agent_instance,
            atune_agent_instance,
            # 安全能力 agent
            secscanner_agent_instance,
            syscare_agent_instance,
            # 操作系统能力 agent
            permissions_agent_instance,
            network_agent_instance,

            #华为云agent
            step_inspector_instance,
            basic_cap_solver_instance, param_asker_instance,
            array_splitter_instance,
            param_inspector_instance,

            check_log_agent_instance,
            #   CES_planner, CES_step_scheduler,
            ECS_planner_instance, ECS_step_scheduler_instance,
            #   EVS_planner, EVS_step_scheduler,
            #   Huawei_Cloud_API_planner, Huawei_Cloud_API_step_scheduler,
            #   IAM_service_planner, IAM_service_step_scheduler,
            IMS_planner_instance, IMS_step_scheduler_instance,
            #   OS_planner, OS_step_scheduler,
            VPC_network_planner_instance, VPC_network_step_scheduler_instance,
            CLUSTER_planner_instance, CLUSTER_step_scheduler_instance,
            NODE_planner_instance, NODE_step_scheduler_instance,


            comprehensive_planner_instance, comprehensive_step_scheduler_instance, text_agent_instance,
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

            [ECS_manager_instance, ECS_harddisk_agent_instance],
            [ECS_manager_instance, ECS_instance_agent_instance],
            [ECS_manager_instance, ECS_netcard_agent_instance],
            [ECS_manager_instance, ECS_recommend_agent_instance],
            [ECS_manager_instance, ECS_specification_query_agent_instance],

            [ECS_harddisk_agent_instance, jobs_agent_instance],
            [ECS_instance_agent_instance, jobs_agent_instance],
            [ECS_netcard_agent_instance, jobs_agent_instance],
            #   [ECS_recommend_agent, job_agent],
            #   [ECS_specification_query_agent,job_agent],

            
            [ECS_specification_query_agent_instance, ECS_manager_instance],
            [ECS_recommend_agent_instance, ECS_manager_instance],
            [ECS_netcard_agent_instance, ECS_manager_instance],
            [ECS_instance_agent_instance, ECS_manager_instance],
            [ECS_harddisk_agent_instance, ECS_manager_instance],

            #   [EVS_manager, EVS_clouddiskt_agent],
            #   [EVS_manager, EVS_snapshot_agent],

            #   [IAM_service_manager, AKSK_agent],

            [IMS_manager_instance, IMS_agent_instance],
            #   [IMS_agent, job_agent],
            [IMS_agent_instance, IMS_manager_instance],

            #   [OS_manager, OS_agent],


            [VPC_network_manager_instance, VPC_secgroup_agent_instance],
            [VPC_network_manager_instance, VPC_subnet_agent_instance],
            [VPC_network_manager_instance, VPC_vpc_agent_instance],

            #   [VPC_secgroup_agent, job_agent],
            #   [VPC_subnet_agent, job_agent],
            #   [VPC_vpc_agent, job_agent],


            [VPC_vpc_agent_instance, VPC_network_manager_instance],
            [VPC_subnet_agent_instance, VPC_network_manager_instance],
            [VPC_secgroup_agent_instance, VPC_network_manager_instance],

            [CLUSTER_manager_instance, CLUSTER_lifecycle_agent_instance],
            [CLUSTER_manager_instance, CLUSTER_specification_change_agent_instance],

            #   [CLUSTER_lifecycle_agent, job_agent],
            #   [CLUSTER_specification_change_agent, job_agent],

            [CLUSTER_lifecycle_agent_instance, CLUSTER_manager_instance],
            [CLUSTER_specification_change_agent_instance, CLUSTER_manager_instance],

            [NODE_manager_instance, NODE_lifecycle_agent_instance],
            [NODE_manager_instance, NODE_pool_agent_instance],
            [NODE_manager_instance, NODE_scaling_protect_agent_instance],

            #   [NODE_lifecycle_agent, job_agent],
            #   [NODE_pool_agent, job_agent],
            #   [NODE_scaling_protect_agent, job_agent],
            
            [NODE_lifecycle_agent_instance, NODE_manager_instance],
            [NODE_pool_agent_instance, NODE_manager_instance],
            [NODE_scaling_protect_agent_instance, NODE_manager_instance],

            
            [ECS_harddisk_agent_instance, API_param_selector_instance],
            [ECS_instance_agent_instance, API_param_selector_instance],
            [ECS_netcard_agent_instance, API_param_selector_instance],
            [ECS_recommend_agent_instance, API_param_selector_instance],
            [ECS_specification_query_agent_instance, API_param_selector_instance],
            [IMS_agent_instance, API_param_selector_instance],
            [VPC_secgroup_agent_instance, API_param_selector_instance],
            [VPC_subnet_agent_instance, API_param_selector_instance],
            [VPC_vpc_agent_instance, API_param_selector_instance],
            [CLUSTER_lifecycle_agent_instance, API_param_selector_instance],
            [CLUSTER_specification_change_agent_instance, API_param_selector_instance],
            [NODE_lifecycle_agent_instance, API_param_selector_instance],
            [NODE_pool_agent_instance, API_param_selector_instance],
            [NODE_scaling_protect_agent_instance, API_param_selector_instance],

            #   [job_agent, API_filler],
            #   [jobs_agent, API_filler],

            [param_selector_instance, array_selector_instance],
            [array_splitter_instance],
            [AKSK_agent_instance],

            # [ECS_manager, param_asker],
            # [IMS_manager, param_asker],
            # [VPC_network_manager, param_asker],
            # [CLUSTER_manager, param_asker],
            # [NODE_manager, param_asker],

            # [leader, simulator],
            # [leader, repeater],
            # [leader, rander],
            # [leader, palindromist]
            user_agent_instance,
            basic_agent_instance

        ]

        thread_strategy = {
            "always_new": [
                (SSHExecuteCommand, check_log_agent),
            ]
        }

        agency = Agency(
            agency_chart=chat_graph,
            thread_strategy=thread_strategy,
            temperature=0.5,
            max_prompt_tokens=25000,
            log_file=log_file,
        )

        plan_agents = {
            "task_planner": task_planner_instance,
            "task_scheduler": task_scheduler_instance,
            "task_inspector": task_inspector_instance,
            "subtask_planner": subtask_planner_instance,
            "subtask_scheduler": subtask_scheduler_instance,
            "subtask_inspector": subtask_inspector_instance,
            "step_inspector": step_inspector_instance,
            "subtask_manager":subtask_manager_instance
        }

        plan_agents_rag = {
            "task_planner_rag": task_planner_rag_instance,
            "task_scheduler_rag": task_scheduler_rag_instance,
            "task_inspector_rag": task_inspector_rag_instance,
        }

        cap_group_agents = {
            #openEuler能力群
            "软件能力群": [software_planner_instance, software_step_scheduler_instance],
            "安全能力群": [security_planner_instance, security_step_scheduler_instance],
            "操作系统能力群": [os_planner_instance, os_step_scheduler_instance],
          
            #华为云能力群
            "弹性云服务器(ECS)管理能力群": [ECS_planner_instance, ECS_manager_instance, ECS_step_scheduler_instance],
            # "云硬盘EVS管理能力群": [EVS_planner, EVS_manager, EVS_step_scheduler],
            # "华为云API处理能力群": [Huawei_Cloud_API_planner, Huawei_Cloud_API_manager, Huawei_Cloud_API_step_scheduler],
            # "统一身份认证服务IAM能力群": [IAM_service_planner, IAM_service_manager, IAM_service_step_scheduler],
            "镜像管理能力群": [IMS_planner_instance, IMS_manager_instance, IMS_step_scheduler_instance],
            # "操作系统管理能力群": [OS_planner, OS_manager, OS_step_scheduler],
            "VPC网络管理能力群": [VPC_network_planner_instance, VPC_network_manager_instance, VPC_network_step_scheduler_instance],
            # "华为云元信息管理能力群": [Huawei_meta_info_planner, ]
            "集群管理能力群": [CLUSTER_planner_instance, CLUSTER_manager_instance, CLUSTER_step_scheduler_instance],
            "节点管理能力群": [NODE_planner_instance, NODE_manager_instance, NODE_step_scheduler_instance],
            "简单任务处理能力群": [basic_cap_solver_instance],
            "综合能力群": [comprehensive_planner_instance, comprehensive_step_scheduler_instance]
        }

        cap_group_agents_rag = {
            "软件能力群": [software_rag_optimizer_instance],
            "安全能力群": [security_rag_optimizer_instance],
            "操作系统能力群": [os_rag_optimizer_instance],
        }

        cap_agents = {
            #openEuler能力群
            "软件能力群": [
                package_agent_instance,
                repository_agent_instance,
                atune_agent_instance,
            ],
            "安全能力群": [
                secscanner_agent_instance,
                syscare_agent_instance,
            ],
            "操作系统能力群": [
                permissions_agent_instance,
                network_agent_instance,
                user_agent_instance,
                basic_agent_instance,
            ],
            #华为云能力群
            "弹性云服务器(ECS)管理能力群": [ECS_harddisk_agent_instance, ECS_instance_agent_instance, ECS_netcard_agent_instance, ECS_recommend_agent_instance, ECS_specification_query_agent_instance],
            # "云硬盘EVS管理能力群": [EVS_clouddiskt_agent, EVS_snapshot_agent],
            # "华为云API处理能力群": [],
            # "统一身份认证服务IAM能力群": [AKSK_agent],
            "镜像管理能力群": [IMS_agent_instance],
            # "操作系统管理能力群": [OS_agent],
            "VPC网络管理能力群": [VPC_secgroup_agent_instance, VPC_subnet_agent_instance, VPC_vpc_agent_instance],
            "集群管理能力群": [CLUSTER_lifecycle_agent_instance, CLUSTER_specification_change_agent_instance],
            "节点管理能力群": [NODE_lifecycle_agent_instance, NODE_pool_agent_instance, NODE_scaling_protect_agent_instance],
            "综合能力群": [text_agent_instance]

        }

        text = """当前账户有一个名为TEST-DB-1的ECS实例，用户名为root ，密码为Abcd1234，其中有MySQL数据库集群，用户名root，密码为YourPass123!,请确认你连接到该MySQL数据库集群并提供当前的集群配置概览。
并基于当前的MySQL集群配置和业务需求，请制定一个异地灾备方案。我们的RTO目标是30分钟，RPO目标是5分钟。请考虑成本效益和性能影响。- 在方案中，请特别说明如何处理跨区域的网络延迟问题。"- "请提供至少两种可选的灾备策略，并分析各自的优缺点。"
之后请构建一个与我们当前生产环境相似的测试环境。生产环境包含2台ECS实例，1个负载均衡器，1个MySQL主从集群，以及相应的VPC和安全组配置。请确保测试环境在功能上与生产环境一致，但可以使用较低配置的资源以节省成本。"
- "在构建测试环境时，请使用以下命名约定：所有资源名称都应该以'TEST-'为前缀。"
- "构建完成后，请提供一份详细的环境对比报告，包括任何与生产环境的差异。"        
 """
        #text = """请获取当前账户的所有ECS服务器信息,若其中没有名为TEST-DB-1的服务器，请创建一个TEST-DB-1的服务器"""
        # text ="""我有一台鲲鹏服务器，操作系统是openEuler22.03，我想在此鲲鹏服务器上安装并配置以下数据库环境：MySQL 8.0.25，设置字符集为 UTF8MB4，端口号为 3306。请确保所有数据库服务均能正常启动，并设置为开机自启动。使用源代码编译方式安装MySQL，已下载MySQL 8.0.25源码在/home/mysql-8.0.25目录下。应该如何操作？"""

        files_path = os.path.join("agents", "files")
        comtext_tree = os.path.join(files_path, "context_tree.json")
        # 确保文件目录存在
        if not os.path.exists(files_path):
            os.mkdir(files_path)
        # 清空context_tree.json
        with open(comtext_tree, "w", encoding="utf-8") as f:
            pass

        request_id = "0"

        while True:
            request_id = str(int(request_id) + 1)
            if use_rag == "True":
                agency.task_planning_rag(
                    original_request=text,
                    plan_agents=plan_agents_rag,
                    cap_group_agents=cap_group_agents_rag,
                    cap_agents=cap_agents,
                    request_id=request_id,
                )
            else:
                agency.task_planning(
                    original_request=text,
                    plan_agents=plan_agents,
                    cap_group_agents=cap_group_agents,
                    cap_agents=cap_agents,
                    request_id=request_id,
                )
            text = input("请输入新的请求描述（或输入exit退出）：")
            log_file.write(text + "\n")
            log_file.flush()
            if text.lower() == "exit":
                break

    finally:
        # 关闭日志文件和恢复标准输出
        sys.stdout = original_stdout
        log_file.close()
        print(f"日志已保存到：{log_file_path}")


if __name__ == "__main__":
    try:
        main()
    finally:  # 响铃
        # import time
        # winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        # time.sleep(2)
        # winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        # time.sleep(2)
        # winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        pass
