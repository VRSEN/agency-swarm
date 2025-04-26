from agency_swarm import Agent, Agency

from agents.task_planner import (
    task_planner, scheduler, inspector
)
from agents.subtask_planner import (
    subtask_planner, subtask_manager, subtask_scheduler, subtask_inspector
)

from agents.k8s_group_agents.pod_manage_group import (
    pod_manage_manager, pod_manage_planner, pod_manage_step_scheduler
)

from agents.k8s_group_agents.pod_orchestration_scheduling_group import (
    pod_orchestration_scheduling_manager,pod_orchestration_scheduling_planner,pod_orchestration_scheduling_step_scheduler
)

from agents.k8s_group_agents.config_manage_group import (
    config_manage_manager, config_manage_planner, config_manage_step_scheduler
)

from agents.k8s_group_agents.storage_group import (
    storage_manager, storage_planner, storage_step_scheduler
)

from agents.k8s_group_agents import step_inspector, basic_cap_solver

from agents.k8s_group_agents.pod_manage_group.pod_manage_agent import pod_manage_agent
from agents.k8s_group_agents.pod_manage_group.resource_grouping_agent import resource_grouping_agent

from agents.k8s_group_agents.pod_orchestration_scheduling_group.stateful_workload_manage_agent import stateful_workload_manage_agent
from agents.k8s_group_agents.pod_orchestration_scheduling_group.stateless_workload_manage_agent import stateless_workload_manage_agent
from agents.k8s_group_agents.pod_orchestration_scheduling_group.task_manage_agent import task_manage_agent
from agents.k8s_group_agents.pod_orchestration_scheduling_group.daemonSet_manage_agent import daemonSet_manage_agent
from agents.k8s_group_agents.pod_orchestration_scheduling_group.affinity_antiAffinity_scheduling_agent import affinity_antiAffinity_scheduling_agent

from agents.k8s_group_agents.config_manage_group.env_config_manage_agent import env_config_manage_agent
from agents.k8s_group_agents.config_manage_group.privacy_manage_agent import privacy_manage_agent


from agents.k8s_group_agents.storage_group.pv_agent import pv_agent
from agents.k8s_group_agents.storage_group.pvc_agent import pvc_agent
from agents.k8s_group_agents.storage_group.storageclass_agent import storageclass_agent
from agents.k8s_group_agents.storage_group.csi_agent import csi_agent
from agents.k8s_group_agents.storage_group.emptydir_agent import emptydir_agent
from agents.k8s_group_agents.storage_group.hostpath_agent import hostpath_agent
from agents.k8s_group_agents.storage_group.disk_agent import disk_agent

from agents.k8s_group_agents import check_log_agent

from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand

from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))

def main():
    task_planner_instance = task_planner.create_agent()
    scheduler_instance = scheduler.create_agent()
    inspector_instance = inspector.create_agent()

    subtask_planner_instance = subtask_planner.create_agent()
    subtask_manager_instance = subtask_manager.create_agent()
    subtask_scheduler_instance = subtask_scheduler.create_agent()
    subtask_inspector_instance = subtask_inspector.create_agent()

    step_inspector_instance = step_inspector.create_agent()

    basic_cap_solver_instance = basic_cap_solver.create_agent()

    pod_manage_manager_instance = pod_manage_manager.create_agent() # ?
    pod_manage_planner_instance = pod_manage_planner.create_agent()
    pod_manage_step_scheduler_instance = pod_manage_step_scheduler.create_agent()
    
    pod_orchestration_scheduling_manager_instance = pod_orchestration_scheduling_manager.create_agent()
    pod_orchestration_scheduling_planner_instance = pod_orchestration_scheduling_planner.create_agent()
    pod_orchestration_scheduling_step_scheduler_instance = pod_orchestration_scheduling_step_scheduler.create_agent()
    
    config_manage_manager_instance = config_manage_manager.create_agent()
    config_manage_planner_instance = config_manage_planner.create_agent()
    config_manage_step_scheduler_instance = config_manage_step_scheduler.create_agent()

    storage_manager_instance = storage_manager.create_agent()
    storage_planner_instance = storage_planner.create_agent()
    storage_step_scheduler_instance = storage_step_scheduler.create_agent()

    pod_manage_agent_instance = pod_manage_agent.create_agent()
    resource_grouping_agent_instance = resource_grouping_agent.create_agent()
    
    stateful_workload_manage_agent_instance = stateful_workload_manage_agent.create_agent()
    stateless_workload_manage_agent_instance = stateless_workload_manage_agent.create_agent()
    task_manage_agent_instance = task_manage_agent.create_agent()
    daemonSet_manage_agent_instance = daemonSet_manage_agent.create_agent()
    affinity_antiAffinity_scheduling_agent_instance = affinity_antiAffinity_scheduling_agent.create_agent()
    
    env_config_manage_agent_instance = env_config_manage_agent.create_agent()
    privacy_manage_agent_instance = privacy_manage_agent.create_agent()

    pv_agent_instance = pv_agent.create_agent()
    pvc_agent_instance = pvc_agent.create_agent()
    storageclass_agent_instance = storageclass_agent.create_agent()
    csi_agent_instance = csi_agent.create_agent()
    emptydir_agent_instance = emptydir_agent.create_agent()
    hostpath_agent_instance = hostpath_agent.create_agent()
    disk_agent_instance = disk_agent.create_agent()

    check_log_agent_instance = check_log_agent.create_agent()

    chat_graph = [
        # task
        task_planner_instance, scheduler_instance, inspector_instance,

        # subtask
        subtask_planner_instance, subtask_manager_instance, subtask_scheduler_instance, subtask_inspector_instance,

        # step
        step_inspector_instance,
        
        # 基本能力群
        basic_cap_solver_instance,
        
        # check log
        check_log_agent_instance,

        # 每个能力群的planner和step scheduler
        pod_manage_planner_instance, pod_manage_step_scheduler_instance,
        pod_orchestration_scheduling_planner_instance, pod_orchestration_scheduling_step_scheduler_instance,
        config_manage_planner_instance, config_manage_step_scheduler_instance,
        storage_planner_instance, storage_step_scheduler_instance,

        # pod管理能力 agent
        pod_manage_agent_instance,
        resource_grouping_agent_instance,
        
        # pod编排调度能力 agent
        stateful_workload_manage_agent_instance,
        stateless_workload_manage_agent_instance,
        task_manage_agent_instance,
        daemonSet_manage_agent_instance,
        affinity_antiAffinity_scheduling_agent_instance,
        
        # 配置管理能力 agent
        env_config_manage_agent_instance,
        privacy_manage_agent_instance,

        # 存储能力 agent
        pv_agent_instance,
        pvc_agent_instance,
        storageclass_agent_instance,
        csi_agent_instance,
        emptydir_agent_instance,
        hostpath_agent_instance,
        disk_agent_instance,
    ]

    thread_strategy = {
        "always_new": [
            (ExecuteCommand, check_log_agent),
        ]
    }

    agency = Agency(agency_chart=chat_graph,
                    thread_strategy=thread_strategy,
                    temperature=0.5,
                    max_prompt_tokens=25000,)

    plan_agents = {
        "task_planner": task_planner_instance,
        "inspector": inspector_instance,
        "scheduler": scheduler_instance,
        "subtask_planner": subtask_planner_instance,
        "subtask_scheduler": subtask_scheduler_instance,
        "subtask_inspector": subtask_inspector_instance,
        "step_inspector": step_inspector_instance
    }

    cap_group_agents = {
        "pod管理能力群": [pod_manage_planner_instance, pod_manage_manager_instance, pod_manage_step_scheduler_instance],
        "pod编排调度能力群": [pod_orchestration_scheduling_planner_instance, pod_orchestration_scheduling_manager_instance, pod_orchestration_scheduling_step_scheduler_instance],
        "配置管理能力群": [config_manage_planner_instance, config_manage_manager_instance, config_manage_step_scheduler_instance],
        "存储能力群": [storage_planner_instance, storage_manager_instance, storage_step_scheduler_instance],
        "简单任务处理能力群": [basic_cap_solver_instance],
    }

    cap_agents = {
        "pod管理能力群": [pod_manage_agent_instance, resource_grouping_agent_instance,],
        "pod编排调度能力群": [stateful_workload_manage_agent_instance, stateless_workload_manage_agent_instance, task_manage_agent_instance, daemonSet_manage_agent_instance, affinity_antiAffinity_scheduling_agent_instance],
        "配置管理能力群": [env_config_manage_agent_instance, privacy_manage_agent_instance],
        "存储能力群": [pv_agent_instance, pvc_agent_instance, storageclass_agent_instance, csi_agent_instance, emptydir_agent_instance, hostpath_agent_instance, disk_agent_instance,],
    }

    # step_json = {
    #     "title": "创建节点",
    #     "id": "step_1",
    #     "agent": ["NODE_lifecycle_agent"],
    #     "description": "在cn-north-4a可用区中，名为ccetest的CCE集群中创建一个节点，节点名字为node-1，集群id为eeb8f029-1c4b-11f0-a423-0255ac100260，节点规格为c6.large.2，系统盘和数据盘大小分别为50GB和100GB，磁盘类型都为SSD，节点通过密码方式登录，用户名为'root', 密码为'JDYkc2FsdCR1SzEzUEgvMy9rOHZRQ0UzRFBEVzFiZm1UMmVZSnFEQjMydzFxOVY5WUt3M2ZmR0JTZWN1N2ZNZlkzYmY5Z2ZDNlJlTHp6NGl3anc3WHM5RDFUcmNuLg=='",
    #     "dep": []
    # }
    # perpared = {
    #     "cap_group": "节点管理能力群",
    #     "step": step_json
    # }
    # agency.test_single_cap_agent(plan_agents=plan_agents, cap_group_agents=cap_group_agents, cap_agents=cap_agents, **perpared)

    text = "在cn-north-4a可用区中，名为ccetest的CCE集群中加入一个节点，节点名字为node-1，集群id为eeb8f029-1c4b-11f0-a423-0255ac100260，节点规格为c6.large.2，系统盘和数据盘大小分别为50GB和100GB，磁盘类型都为SSD"
    # text = "在cn-north-4a可用区创建一个名为ccetest的CCE集群，最小规格；未创建vpc和子网，需要创建名为vpc111的vpc和名为subnet111的子网，vpc的cidr为192.168.0.0/24，网关ip为192.168.0.1; 之后你需要在该CCE集群中加入三个节点"
    # text = "在北京cn-north-4a可用区创建一个最低规格的CCE，名为'ccetest'，已有vpc和子网，VPC id为8bf558f4-2f96-4248-9cb0-fee7a2a6cebb，子网id为0519a325-6fa3-4f68-83ec-6f13263167d2"
    # text = "创建一个8核32g的ECS，操作系统选择为Ubuntu 20.04。"
    # text = "在北京可用区创建三个ecs，之后删除创建时间超过5分钟的ecs"
    # text = "在华为云ecs上部署mysql和postgresql，并用sysbench测试它们的性能"
    # text = input("👤 USER: ")

    agency.task_planning(original_request=text, plan_agents=plan_agents, cap_group_agents=cap_group_agents, cap_agents=cap_agents)

if __name__ == "__main__":
    main()