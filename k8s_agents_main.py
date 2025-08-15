from agency_swarm import Agent, Agency

from agents.k8s_group_agents.task_planner import (
    task_planner, task_scheduler, task_inspector
)
from agents.k8s_group_agents.subtask_planner import (
    subtask_planner, subtask_scheduler, subtask_inspector
)

from agents.k8s_group_agents.comprehensive_group import(
    comprehensive_planner, comprehensive_step_scheduler
)

from agents.k8s_group_agents.pod_manage_group import (
    pod_manage_planner, pod_manage_step_scheduler
)

from agents.k8s_group_agents.pod_orchestration_scheduling_group import (
    pod_orchestration_scheduling_planner,pod_orchestration_scheduling_step_scheduler
)

from agents.k8s_group_agents.config_manage_group import (
    config_manage_planner, config_manage_step_scheduler
)

from agents.k8s_group_agents.monitor_group import (
    monitor_planner, monitor_step_scheduler
)

from agents.k8s_group_agents.software_manage_group import (
    software_manage_planner, software_manage_step_scheduler
)

from agents.k8s_group_agents.storage_group import (
    storage_planner, storage_step_scheduler
)

from agents.k8s_group_agents import step_inspector

from agents.k8s_group_agents.comprehensive_group.file_io_agent import file_io_agent
from agents.k8s_group_agents.comprehensive_group.text_output_agent import text_output_agent

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

from agents.k8s_group_agents.monitor_group.monitor_configuration_agent import monitor_configuration_agent
from agents.k8s_group_agents.monitor_group.monitor_observe_agent import monitor_observe_agent
from agents.k8s_group_agents.monitor_group.flexible_strategy_manage_agent import flexible_strategy_manage_agent


from agents.k8s_group_agents.software_manage_group.software_config_modify_agent import software_config_modify_agent
from agents.k8s_group_agents.software_manage_group.software_install_agent import software_install_agent
from agents.k8s_group_agents.software_manage_group.software_monitor_agent import software_monitor_agent
from agents.k8s_group_agents.software_manage_group.stress_test_agent import stress_test_agent

from agents.k8s_group_agents.vm_group.kubeadm_agent import kubeadm_agent
from agents.k8s_group_agents.vm_group.status_agent import status_agent
from agents.k8s_group_agents.vm_group.package_agent import package_agent

from agents.k8s_group_agents import check_log_agent

from agents.k8s_group_agents.tools.ExecuteCommand import ExecuteCommand


from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os
import sys
import datetime

from agents.k8s_group_agents.vm_group import vm_planner, vm_step_scheduler

load_dotenv()
set_openai_key(os.getenv('OPENAI_API_KEY'))

def main():
    # 添加日志功能：创建一个日志文件，用当前时间作为文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join("log", f"run_log_{timestamp}.txt")
    # 创建日志文件
    log_file = open(log_file_path, 'w', encoding='utf-8', buffering=1)
    
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
    
    try:
        # 以下是日志功能更新前的代码
        task_planner_instance = task_planner.create_agent()
        task_scheduler_instance = task_scheduler.create_agent()
        task_inspector_instance = task_inspector.create_agent()

        subtask_planner_instance = subtask_planner.create_agent()
        subtask_scheduler_instance = subtask_scheduler.create_agent()
        subtask_inspector_instance = subtask_inspector.create_agent()

        step_inspector_instance = step_inspector.create_agent()

        comprehensive_planner_instance = comprehensive_planner.create_agent()
        comprehensive_step_scheduler_instance = comprehensive_step_scheduler.create_agent()
        pod_manage_planner_instance = pod_manage_planner.create_agent()
        pod_manage_step_scheduler_instance = pod_manage_step_scheduler.create_agent()
        pod_orchestration_scheduling_planner_instance = pod_orchestration_scheduling_planner.create_agent()
        pod_orchestration_scheduling_step_scheduler_instance = pod_orchestration_scheduling_step_scheduler.create_agent()
        config_manage_planner_instance = config_manage_planner.create_agent()
        config_manage_step_scheduler_instance = config_manage_step_scheduler.create_agent()
        storage_planner_instance = storage_planner.create_agent()
        storage_step_scheduler_instance = storage_step_scheduler.create_agent()
        monitor_planner_instance = monitor_planner.create_agent()
        monitor_step_scheduler_instance = monitor_step_scheduler.create_agent()
        software_manage_planner_instance = software_manage_planner.create_agent()
        software_manage_step_scheduler_instance = software_manage_step_scheduler.create_agent()

        #虚拟机子任务规划
        vm_planner_instance = vm_planner.create_agent()
        vm_step_scheduler_instance = vm_step_scheduler.create_agent()

        text_output_agent_instance =  text_output_agent.create_agent()
        file_io_agent_instance = file_io_agent.create_agent()

        pod_manage_agent_instance = pod_manage_agent.create_agent()
        resource_grouping_agent_instance = resource_grouping_agent.create_agent()

        stateful_workload_manage_agent_instance = stateful_workload_manage_agent.create_agent()
        stateless_workload_manage_agent_instance = stateless_workload_manage_agent.create_agent()
        task_manage_agent_instance = task_manage_agent.create_agent()
        daemonSet_manage_agent_instance = daemonSet_manage_agent.create_agent()
        affinity_antiAffinity_scheduling_agent_instance = affinity_antiAffinity_scheduling_agent.create_agent()

        env_config_manage_agent_instance = env_config_manage_agent.create_agent()
        privacy_manage_agent_instance = privacy_manage_agent.create_agent()

        monitor_configuration_agent_instance = monitor_configuration_agent.create_agent()
        monitor_observe_agent_instance = monitor_observe_agent.create_agent()
        flexible_strategy_manage_agent_instance = flexible_strategy_manage_agent.create_agent()

        software_config_modify_agent_instance = software_config_modify_agent.create_agent()
        software_install_agent_instance = software_install_agent.create_agent()
        software_monitor_agent_instance = software_monitor_agent.create_agent()
        stress_test_agent_instance = stress_test_agent.create_agent()

        pv_agent_instance = pv_agent.create_agent()
        pvc_agent_instance = pvc_agent.create_agent()
        storageclass_agent_instance = storageclass_agent.create_agent()
        csi_agent_instance = csi_agent.create_agent()
        emptydir_agent_instance = emptydir_agent.create_agent()
        hostpath_agent_instance = hostpath_agent.create_agent()
        disk_agent_instance = disk_agent.create_agent()

        check_log_agent_instance = check_log_agent.create_agent()

        # 虚拟机智能体初始化
        status_agent_instance = status_agent.create_agent()
        kubeadm_agent_instance = kubeadm_agent.create_agent()
        package_agent_instance = package_agent.create_agent()

        chat_graph = [
            # task
            task_planner_instance, task_scheduler_instance, task_inspector_instance, 

            # subtask
            subtask_planner_instance, subtask_scheduler_instance, subtask_inspector_instance,

            # step
            step_inspector_instance,
            
            # check log
            check_log_agent_instance,
            #
            # # 每个能力群的planner和step scheduler
            
            pod_manage_planner_instance, pod_manage_step_scheduler_instance,
            pod_orchestration_scheduling_planner_instance, pod_orchestration_scheduling_step_scheduler_instance,
            config_manage_planner_instance, config_manage_step_scheduler_instance,
            storage_planner_instance, storage_step_scheduler_instance,
            monitor_planner_instance, monitor_step_scheduler_instance,
            software_manage_planner_instance, software_manage_step_scheduler_instance,
            vm_planner_instance, vm_step_scheduler_instance,
            comprehensive_planner_instance,comprehensive_step_scheduler_instance,
            #
            # # 综合能力 agent
            file_io_agent_instance,
            text_output_agent_instance,

            # # pod管理能力 agent
            pod_manage_agent_instance,
            resource_grouping_agent_instance,
            #
            # # pod编排调度能力 agent
            stateful_workload_manage_agent_instance,
            stateless_workload_manage_agent_instance,
            task_manage_agent_instance,
            daemonSet_manage_agent_instance,
            affinity_antiAffinity_scheduling_agent_instance,
            #
            # # 配置管理能力 agent
            env_config_manage_agent_instance,
            privacy_manage_agent_instance,
            #
            # # 存储能力 agent
            pv_agent_instance,
            pvc_agent_instance,
            storageclass_agent_instance,
            csi_agent_instance,
            emptydir_agent_instance,
            hostpath_agent_instance,
            disk_agent_instance,
            #
            # # 监控能力 agent
            monitor_configuration_agent_instance,
            monitor_observe_agent_instance,
            flexible_strategy_manage_agent_instance,
            #
            # # 软件管理能力 agent
            software_config_modify_agent_instance,
            software_install_agent_instance,
            software_monitor_agent_instance,
            stress_test_agent_instance,
            #
            ## 虚拟机交互能力agent
            kubeadm_agent_instance,
            package_agent_instance,
            status_agent_instance
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
            "task_scheduler": task_scheduler_instance,
            "task_inspector": task_inspector_instance,
            "subtask_planner": subtask_planner_instance,
            "subtask_scheduler": subtask_scheduler_instance,
            "subtask_inspector": subtask_inspector_instance,
            "step_inspector": step_inspector_instance
        }

        cap_group_agents = {
            "pod管理能力群": [pod_manage_planner_instance, pod_manage_step_scheduler_instance],
            "pod编排调度能力群": [pod_orchestration_scheduling_planner_instance, pod_orchestration_scheduling_step_scheduler_instance],
            "配置管理能力群": [config_manage_planner_instance, config_manage_step_scheduler_instance],
            "存储能力群": [storage_planner_instance, storage_step_scheduler_instance],
            "监控能力群": [monitor_planner_instance,monitor_step_scheduler_instance],
            "软件管理能力群": [software_manage_planner_instance, software_manage_step_scheduler_instance],
            "虚拟机交互能力群":[vm_planner_instance, vm_step_scheduler_instance],
            "综合能力群":[comprehensive_planner_instance,comprehensive_step_scheduler_instance]
        }

        cap_agents = {
            "pod管理能力群": [pod_manage_agent_instance, resource_grouping_agent_instance,],
            "pod编排调度能力群": [stateful_workload_manage_agent_instance, stateless_workload_manage_agent_instance, task_manage_agent_instance, daemonSet_manage_agent_instance, affinity_antiAffinity_scheduling_agent_instance],
            "配置管理能力群": [env_config_manage_agent_instance, privacy_manage_agent_instance],
            "监控能力群": [monitor_configuration_agent_instance, monitor_observe_agent_instance,flexible_strategy_manage_agent_instance],
            "软件管理能力群": [software_config_modify_agent_instance, software_install_agent_instance, software_monitor_agent_instance],
            "存储能力群": [pv_agent_instance, pvc_agent_instance, storageclass_agent_instance, csi_agent_instance, emptydir_agent_instance, hostpath_agent_instance, disk_agent_instance,],
            "虚拟机交互能力群":[package_agent_instance, status_agent_instance,kubeadm_agent_instance],
            "综合能力群":[file_io_agent_instance,text_output_agent_instance]
        }

        text = """
        对mysql进行高吞吐量测试
使用 JMeter 执行挂载于pod-name上的/jmeter/test-plan.jmx文件，并根据结果生成报告

        """
        # text = input("请输入新的请求描述（或输入exit退出）：")

        files_path = os.path.join("agents", "files")
        context_path = os.path.join(files_path, "context.json")
        # 确保文件目录存在
        if not os.path.exists(files_path):  
            os.mkdir(files_path)    
        # 清空context.json
        with open(context_path, "w", encoding='utf-8') as f:
            pass

        request_id = 0

        while True:
            request_id += 1
            agency.task_planning(original_request=text, plan_agents=plan_agents, cap_group_agents=cap_group_agents, cap_agents=cap_agents, request_id=request_id)
            text= input("请输入新的请求描述（或输入exit退出）：")
            log_file.write(text + '\n')
            log_file.flush()
            if text.lower() == 'exit':
                break
            
    
    finally:
        # 关闭日志文件和恢复标准输出
        sys.stdout = original_stdout
        log_file.close()
        print(f"日志已保存到：{log_file_path}")

if __name__ == "__main__":
    try:
        main()
    finally: # 响铃
        import winsound
        import time
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        time.sleep(2)
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        time.sleep(2)
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
