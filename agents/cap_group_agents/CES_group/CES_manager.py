from agency_swarm import Agent
from agents.cap_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "CES_manager"

_description = """
负责云监控CES能力群的步骤规划
"""

_group_name = "云监控CES能力群"

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_agents = """
1. **MonitorEvent Agent**: 专门负责处理华为云的事件监控管理相关操作，。
2. **MonitorAlarmRule Agent**: 专门负责处理华为云的告警规则管理相关操作。
3. **MonitorAlarmHistory Agent**: 专门负责处理华为云的告警记录查询相关操作。
4. **MonitorData Agent**: 专门负责处理华为云的监控数据管理相关操作。
5. **MonitorDashboard Agent**: 专门负责处理华为云的监控看板及视图管理相关操作。
6. **MonitorMetric Agent**: 专门负责处理华为云的监控指标管理相关操作。
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