from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "subtask_inspector"

_description = """
职责是检查subtask_planner规划的任务是否合理
"""
_input_format = """
{
    "user_request": ...,
    "task_graph": {
        "subtask_1": {
            "title": 任务名称,
            "id": 任务ID, 
            "capability_group": <能力群名称>,
            "description": 任务描述, 
            "dep": <前置任务ID列表>
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

_instruction = f"""作为审查者，你将从subtask_planner那里收到一个 JSON 格式的任务规划结果 <task_graph> 和原始任务请求 <user_request>。
输入格式为:
{_input_format}

注意：每次得到输入时，你都需要通过`ReadJsonFile`从context_tree.json中读取已完成的所有步骤所产生的上下文信息。

请严谨专业地一步步思考: 
1. 首先，你需要确保**输入中的 <task_graph> 是JSON格式**；
2. 你需要检查<user_request>是否可以分解为<task_graph>，且确保<task_graph>任务的拆分和执行顺序合理；
3. 确保<task_graph>中所有操作都可通过**回复中文文字或执行命令行**实现；
4. 你需要保证<task_graph>中没有**多余**的确认或查询步骤，如确认资源是否存在等；
5. 确保<task_graph>中每个子任务的执行能力群"capability_group"名称正确且合理，所有能力群名称和介绍如下：
    a. "软件能力群": 负责软件包管理、代码仓库管理、软件配置优化（A-Tune工具）；
    b. "安全能力群": 负责漏洞扫描（secScanner工具）、漏洞修复（SysCare工具）；
    c. "远程控制访问能力群": 负责用户和文件等权限管理、网络及防火墙管理。

你应该按照以下json格式评估<task_graph>: 
{_output_format}

如果任务拆分和流程合理，请在"review"字段填入"YES"；如果任务拆分和流程有问题，请在"review"字段填入"NO"，并在"explain"字段填入你觉得不合理的原因。
"""

# 4. 除非<user_request>或context_index.json中有说明，否则任务执行环境最开始应该没有创建**任何资源**，确保每个任务所需资源应该在**前置任务**或**已完成任务**中有所创建；

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