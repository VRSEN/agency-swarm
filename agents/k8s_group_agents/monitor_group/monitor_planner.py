from agency_swarm import Agent
from agents.k8s_group_agents.planner_instruction import planner_instruction
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "monitor_planner"

_description = """
负责监控能力群的步骤规划
"""

_group_name = "监控能力群"

_input_format = """
{
    "title": <本次子任务的名称>,
    "description": <本次子任务的描述>
}
"""

_agents = """
1. **monitor_configuration_agent**: 负责修改k8s集群的插件或配置文件。
2. **monitor_observe_agent**: 负责对k8s集群的健康、监控、日志（LTS）、告警（AOM）进行观测。
3. **flexible_strategy_manage_agent**：负责管理 HPA/VPA 策略，基于 Prometheus 指标进行自动扩缩容决策。
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