from agency_swarm import Agent
from agents.k8s_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "comprehensive_planner"

_description = """
负责综合能力群的步骤规划
"""

_group_name = "综合能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>
}
"""

_agents = """
1. **text_output_agent**：负责根据用户输入生成相应文本。
2. **file_io_agent**：负责读写k8s环境中的文件
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

__instruction = f""" 
# 注意，类似于“收集和分析测试结果”的任务请分为读取结果和分析结果等多个步骤进行。
# 注意， 规划前请分清输出文本的位置，所有要输出到k8s环境中的文本都应用**file_io_agent**输出
# 注意，类似于创建测试文件的任务请直接交由**file_io_agent**进行

#"""

_instruction = planner_instruction(_group_name, _input_format, _agents, _output_format)+ __instruction


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