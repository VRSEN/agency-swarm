from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "step_inspector"

_description = """
职责是检查step_planner规划的任务是否合理
"""
_input_format = """
{
    "user_request": ...,
    "task_graph": {
        "step_1": {
            "title": 步骤名称,
            "id": 步骤ID, 
            "agent": [agent_name_1, ...],
            "description": 步骤描述, 
            "dep": <前置步骤ID列表>,
        },
        ...
    }
}
"""

_output_format = """
{
    "review": "YES"/"NO",
    "explain": <解释原因>
}
"""

_instruction = f"""
作为审查者，你将从task_planner那里收到一个 JSON 格式的任务规划结果 <task_graph> 和原始用户请求 <user_request>。
输入格式为:
{_input_format}

你需要通过`ReadJsonFile`从context.json中读取已有环境中的上下文信息

请一步步思考: 
0. 你需要确保输入中的 <task_graph> 是JSON格式；
1. 你需要检查<user_request>是否可以分解为<task_graph>，且确保<task_graph>任务的拆分和执行顺序合理；
2. 确保<task_graph>中没有**不通过华为云API或ssh连接命令行指令或编写、运行脚本**实现的操作；
3. 确保用户隐私，环境中已经有华为云访问认证等认证信息，且已经被所需agent得知，确保任务规划中没有获取访问凭证等类似步骤；
4. 除非<user_request>或context.json中有说明，否则任务执行环境最开始应该没有创建**任何资源**，确保每个任务所需资源应该在**前置任务**中有所创建；
5. 你需要保证任务规划中没有**多余**的确认或查询步骤

你应该按照以下json格式评估TASK: 
{_output_format}

如果任务拆分和流程合理，请在"review"字段填入"YES"；如果任务流程有问题，请在"review"字段填入"NO"，并在"explain"字段填入你觉得不合理的原因

"""


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