from agency_swarm import Agent
from agents.k8s_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "software_manage_planner"

_description = """
负责软件管理能力群的步骤规划
"""

_group_name = "软件管理能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
    "total_subtask_graph": <所有子任务的规划图>,
}
"""

_agents = """
1. **software_config_modify_agent**: 负责对k8s集群中的软件配置进行修改。
2. **software_install_agent**: 负责进行k8s集群中软件的安装。
3. **software_monitor_agent**: 负责对k8s集群中的软件进行监控。
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