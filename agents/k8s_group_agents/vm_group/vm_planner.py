from agency_swarm import Agent
from agents.k8s_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "vm_planner"

_description = """
负责虚拟机交互能力群的步骤规划
"""

_group_name = "虚拟机交互能力群"

_input_format = """
{
    "title": <本次子任务的名称>,
    "description": <本次子任务的描述>,
    "total_subtask_graph": <所有子任务的规划图>
}
"""

_agents = """
1. **package_agent**: 负责在**虚拟机**上使用apt等包管理器对虚拟机上的软件包进行查询、安装、删除等操作。
2. **kubeadm_agent**: 负责在**虚拟机**上使用kubeadm相关命令实现虚拟机与k8s集群进行通信，例如使用kubeadm join命令将当前节点加入到集群中。
3. **status_agent**: 负责在**虚拟机**上使用systemctl等命令查看指定软件和进程的运行状况。
"""

_output_format = """
{
    "step_1": {
        "title": 步骤名称,
        "id": 步骤ID, 
        "agent": [agent_name_1, ...],
        "description": 步骤描述, 
        "dep": <前置步骤ID列表>
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