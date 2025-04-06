from agency_swarm.agents import Agent
from agents.basic_agents.api_agents.tools.CheckParamRequired import CheckParamRequired

_name = "Param Inspector"

_description = "Param Inspector负责检查Param Selector的输出，确认是否需要该参数"


_instructions = f"""
你的职责是根据接收到的输入来判断是否需要某个参数，你需要严格按照以下步骤执行：

你需要仔细认真地思考输入的内容。

# 注意: 你只需要考虑输入的内容信息，不允许向用户询问信息

如果输入的意思是不需要该参数，你应该直接输出"不需要该参数"

如果输入的意思是需要该参数，你应该直接输出"需要该参数"

"""

_tools = [CheckParamRequired]

_files_folder = ""

def create_agent(*,
                 name=_name,
                 description=_description,
                 instructions=_instructions,
                 tools=_tools,
                 files_folder=_files_folder):
    return Agent(name=name,
                 tools=tools,
                 description=description,
                 instructions=instructions,
                 files_folder=files_folder,
                 temperature=0.5,
                 max_prompt_tokens=25000,
                 )
