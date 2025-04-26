from agency_swarm import Agent
from agents.k8s_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "pod_orchestration_scheduling_planner"

_description = """
负责pod编排调度能力群的步骤规划
"""

_group_name = "pod编排调度能力群"

_input_format = """
{
    "total_subtask_graph": <所有子任务的规划图>,
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

# TODO
_agents = """
1. **stateless_workload_manage_agent**: 负责k8s集群的pod的无状态负载管理任务，包括：1.Deployment创建、查询、删除；2. ReplicaSer查询；3. 升级策略管理，例如RollingUpdate、Recreate等；4.回滚。
2. **stateful_workload_manage_agent**: 负责k8s集群的pod的有状态工作负载管理任务，包括：1.Stateful创建、查询、删除；2.Headless ServiceH创建；3.pod挂载存储管理
3. **task_manage_agent**: 负责k8s集群的pod的任务管理，包括：1.普通任务创建；2.CronJob创建，例如定时设置
4. **daemonSet_manage_agent**: 负责k8s集群的pod的守护进程集管理，包括：1.DaemonSet创建、查询、删除；2.nodeSelector管理
5. **affinity_antiAffinity_scheduling_agent**: 负责k8s集群的pod的亲和和反亲和调度，包括：1.强制选择；2.优先选择
"""

_output_format = """
{
    "step_1": {
        "title": 步骤名称,
        "id": 步骤ID, 
        "agent": [agent_name_1, ...],
        "description": 步骤描述, 
        "dep": <前置步骤ID列表>,
    },
    ...
}
"""

_instruction = planner_instruction(_group_name, _input_format, _agents, _output_format)


_tools = [ReadJsonFile]

_file_folder = ""

def create_agent(*, 
                 description=_description, 
                 instuction=_instruction, 
                 tools=_tools, 
                 files_folder=_file_folder):
    return Agent(name=_name,
                 tools=tools,
                 description=description,
                 instructions=instuction,
                 files_folder=_file_folder,
                 temperature=0.5,
                 response_format='auto',
                 max_prompt_tokens=25000,)