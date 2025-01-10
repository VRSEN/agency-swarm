from agency_swarm import Agent
from agents.cap_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "IMS_planner"

_description = """
负责镜像管理能力群的步骤规划
"""

_group_name = "镜像管理能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **IMS_agent**: 负责华为云镜像资源管理任务，包括:查询镜像列表，更新镜像信息，制作像，镜像文件快速导入，使用外部镜像文件制作数据镜像，制作整机镜像，注册镜像，导出镜像，查询镜像支持的OS列表。
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