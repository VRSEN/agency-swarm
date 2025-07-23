from agency_swarm import Agent, Agency

from agents.openeuler_agents.task_planner import (
    task_planner, task_scheduler, task_inspector
)
from agents.openeuler_agents.subtask_planner import (
    subtask_planner, subtask_scheduler, subtask_inspector
)

from agents.openeuler_agents.software_group import (
    software_planner, software_step_scheduler
)

from agents.openeuler_agents.security_group import (
    security_planner, security_step_scheduler
)

from agents.openeuler_agents.os_group import (
    os_planner, os_step_scheduler
)

from agents.openeuler_agents import step_inspector

from agents.openeuler_agents.software_group.package_agent import package_agent
from agents.openeuler_agents.software_group.repository_agent import repository_agent
from agents.openeuler_agents.software_group.atune_agent import atune_agent

from agents.openeuler_agents.security_group.secscanner_agent import secscanner_agent
from agents.openeuler_agents.security_group.syscare_agent import syscare_agent

from agents.openeuler_agents.os_group.permissions_agent import permissions_agent
from agents.openeuler_agents.os_group.network_agent import network_agent

from agents.openeuler_agents import check_log_agent

from agents.openeuler_agents.tools.SSHExecuteCommand import SSHExecuteCommand


from agency_swarm import set_openai_key

from dotenv import load_dotenv
import os
import sys
import datetime

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

        check_log_agent_instance = check_log_agent.create_agent()

        chat_graph = [
            # task
            task_planner_instance, task_scheduler_instance, task_inspector_instance, 

            # subtask
            subtask_planner_instance, subtask_scheduler_instance, subtask_inspector_instance,

            # step
            step_inspector_instance,
            
            # check log
            check_log_agent_instance,

            # 每个能力群的planner和step scheduler
            software_planner_instance, software_step_scheduler_instance,
            security_planner_instance, security_step_scheduler_instance,
            os_planner_instance, os_step_scheduler_instance,

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
        ]

        thread_strategy = {
            "always_new": [
                (SSHExecuteCommand, check_log_agent),
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
            "软件能力群": [software_planner_instance, software_step_scheduler_instance],
            "安全能力群": [security_planner_instance, security_step_scheduler_instance],
            "操作系统能力群": [os_planner_instance, os_step_scheduler_instance],
        }

        cap_agents = {
            "软件能力群": [package_agent_instance, repository_agent_instance, atune_agent_instance,],
            "安全能力群": [secscanner_agent_instance, syscare_agent_instance,],
            "操作系统能力群": [permissions_agent_instance, network_agent_instance,],
        }

        text ="""在OpenEuler系统上使用yum安装redis6软件包。"""

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
            text = input("请输入新的请求描述（或输入exit退出）：")
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
