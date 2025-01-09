from agency_swarm.agents import Agent
from agents.cap_group_agents.IAM_service_group.cap_agents.AKSK_agent.tools.GetCredentials import GetCredentials

_name = "AKSK_agent"

_description = "AKSK Agent 提供登录认证信息。"

_instructions = """
你的任务是**调用函数**`GetCredentials()`获取 access_key 和 secret_key，你的输出格式为:
{
    "result": "SUCCESS"/"FAIL",
    "context": {
        "access_key": <access_key>,
        "secret_key": <secret_key>
    }
}
其中，result字段需要填入是否成功获取AK/SK的值，context字段填入具体的你获取的AK/SK
"""

_tools = [GetCredentials]

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
                 response_format={'type': 'json_object'},
                 max_prompt_tokens=25000,
                 )
