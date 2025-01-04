from agency_swarm import Agent
from agents.cap_group_agents.manager_instruction import manager_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "CES_manager"

_description = """
负责云监控CES能力群的消息管理
"""

_group_name = "云监控CES能力群"

_instruction = manager_instruction(_group_name)

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