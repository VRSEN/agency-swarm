from agency_swarm.agents import Agent
from agents.cap_group_agents.IAM_service_group.cap_agents.AKSK_agent.tools.GetCredentials import GetCredentials

_name = "AKSK Agent"

_description = "AKSK Agent 提供登录认证信息。"

_instructions = """你的任务是**调用函数**`GetCredentials()`获取 access_key 和 secret_key，并以json格式输出。"""

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
