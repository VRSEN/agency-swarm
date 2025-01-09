from agency_swarm import Agent
from agents.cap_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "ECS_planner"

_description = """
负责弹性云服务器(ECS)管理能力群的步骤规划
"""

_group_name = "弹性云服务器(ECS)管理能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **ECS_instance_agent**: 负责ECS实例生命周期管理任务，包括：创建云服务器，删除云服务器，创建云服务器（按需），查询云服务器详细信息，查询云服务器详情列表，查询云服务器列表，修改云服务器，冷迁移云服务器，批量启动云服务器，批量关闭云服务器，批量重启云服务器。
2. **ECS_specification_query_agent**: 负责华为云ECS规格信息查询任务，包括：查询规格详情和规格扩展信息列表，查询规格销售策略， 查询云服务器规格变更支持列表。
3. **ECS_netcard_agent**: 负责华为云ECS网卡管理任务，包括：批量添加云服务器网卡、批量删除云服务器网卡，查询云服务器网卡信息，云服务器切换虚拟私有云，更新云服务器指定网卡属性。
4. **ECS_harddisk_agent**: 负责华为云ECS硬盘管理任务，包括：查询弹性云服务器单个磁盘信息、查询弹性云服务器挂载磁盘列表信息，查询弹性云服务器挂载磁盘列表详情信息，弹性云服务器挂载磁盘、弹性云服务器卸载磁盘，修改弹性云服务器挂载的单个磁盘信息。
5. **ECS_recommend_agent**: 负责华为云ECS规格推荐任务，包括：地域推荐。
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