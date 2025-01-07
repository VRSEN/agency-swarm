from agency_swarm import Agent
from agents.cap_group_agents.CES_group.cap_agents.monitor_alarm_history_agent.tools import (
    ReadLog, WriteLog
)

_name = "CES_alarm_history_agent"

_description = """
负责华为云的告警记录查询管理任务，包括：查询告警记录列表。
"""

_instruction = "./instructions.md"

_tools = [ReadLog, WriteLog]

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