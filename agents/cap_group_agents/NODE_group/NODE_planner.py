from agency_swarm import Agent
from agents.cap_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "NODE_planner"

_description = """
负责节点管理能力群的步骤规划
"""

_group_name = "节点管理能力群"

_input_format = """
{
    "total_subtask_graph": <所有子任务的规划图>,
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **NODE_lifecycle_agent**: 负责k8s集群节点生命周期管理任务，包括：创建节点，获取指定的节点，获取集群下所有节点，更新指定的节点，删除节点，纳管节点，重置节点，同步节点，批量同步节点。
2. **NODE_pool_agent**: 负责k8s集群节点池管理任务，包括：创建节点池，获取指定的节点池，获取集群下所有节点池，更新指定节点池，删除节点池，查询指定节点池支持配置的参数列表，查询指定节点池支持配置的参数内容，修改指定节点池配置参数的值，伸缩节点池，同步节点池。
3. **NODE_scaling_protect_agent**: 负责k8s集群节点缩容保护任务，包括：节点开启缩容保护，节点关闭缩容保护。
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