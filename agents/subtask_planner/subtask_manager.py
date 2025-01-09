from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "subtask_manager"

_description = """
职责是负责能力群之间的消息管理
"""

_input_format = """
{
    "result": "SUCCESS"/"FAIL",
    "context": <上下文信息或ERROR信息>
}
"""

_output_format = """
{
    "subtask_1": {
        "title": 任务名称,
        "id": 任务ID, 
        "capability_group": <能力群名称>,
        "description": 任务描述, 
        "dep": <前置任务ID列表>,
    },
    ...
}
"""

_instruction = f"""
作为子任务规划者，你将接收到来自能力群manager的消息

能力群manager的消息可能是请求或者任务执行信息


"""


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