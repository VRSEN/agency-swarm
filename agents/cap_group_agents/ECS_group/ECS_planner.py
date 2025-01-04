from agency_swarm import Agent
from agents.cap_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "ECS_planner"

_description = """
负责ECS能力群的步骤规划
"""

_group_name = "弹性云服务器(ECS)管理能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **ECS Agent**: 负责创建、删除、查询、修改、迁移、启动、停止、重启ECS实例；
2. **Information Agent**: 负责查询华为云ECS相关的规格信息；
3. **Netcard Agent**: 负责ECS网卡配置；
4. **Harddisk Agent**: 负责ECS硬盘配置；
5. **Recommend Agent**: 负责根据Information Agent查询结果，进行华为云ECS规格推荐；
6. **Daemon Agent**: 负责对已创建华为云ECS进行信息管理，记录日志。
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