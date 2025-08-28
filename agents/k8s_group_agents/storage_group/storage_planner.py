from agency_swarm import Agent
from agents.k8s_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "storage_planner"

_description = """
负责存储能力群的步骤规划
"""

_group_name = "存储能力群"

_input_format = """
{
    "title": <本次子任务的名称>,
    "description": <本次子任务的描述>
}
"""

_agents = """
1. **pv_agent**: 负责PersistentVolume的管理，包括创建、查询、修改和删除。
2. **pvc_agent**: 负责PersistentVolumeClaim的管理，包括创建、查询、绑定和删除。
3. **storageclass_agent**: 负责StorageClass的管理，包括创建、查询、修改和删除。
4. **csi_agent**: 负责CSI的管理，包括各种CSI插件、CSI相关资源、适配存储类型。
5. **emptydir_agent**: 负责EmptyDir的管理，包括查询状态、检查异常、修改配置。
6. **hostpath_agent** 负责HostPath的管理，包括查询状态、修改配置。
7. **disk_agent**: 负责磁盘管理，包括挂载、卸载、查询状态、故障隔离。
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
                 files_folder=_file_folder,
                 temperature=0.5,
                 response_format='auto',
                 max_prompt_tokens=25000,)