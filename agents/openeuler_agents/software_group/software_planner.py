from agency_swarm import Agent
from agents.openeuler_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "software_planner"

_description = """
负责软件能力群的步骤规划
** 注意**
1. ssh客户端不保存状态，规划的时候不要单独规划 **进入目录**步骤，应该与具体的执行步骤合并。
"""

_group_name = "软件能力群"

_input_format = """
{
    "title": <本次子任务的名称>,
    "description": <本次子任务的描述>,
    "total_subtask_graph": <所有子任务的规划图>
}
"""

_agents = """
1. **package_agent**: 负责使用yum等包管理器对软件包进行查询、安装、删除等操作。
2. **repository_agent**: 负责使用git管理代码仓库的更改，例如导出commit等。
3. **atune_agent**: 负责使用A-Tune工具优化OpenEuler系统上的软件配置，提升应用性能。
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
                 files_folder=files_folder,
                 temperature=0.5,
                 response_format='auto',
                 max_prompt_tokens=25000,)