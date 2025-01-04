from agency_swarm import Agent
from agents.cap_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "IAM_service_planner"

_description = """
负责统一身份认证IAM能力群的步骤规划
"""

_group_name = "统一身份认证IAM能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **AKSK_Agent**: 负责华为云账户信息管理，包括获取AK和SK，用于身份验证和授权
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
                 response_format={"type": "json_object"},
                 max_prompt_tokens=25000,)