from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
_name = "task_planner"

_description = """
职责是根据用户请求规划任务
"""
_input_format = """
"""

_output_format = """
{
    "task_1": {
        "title": 任务名称,
        "id": 任务ID, 
        "description": 任务的详细描述, 
        "dep": <前置任务ID列表>
    },
    ...
}
"""

_instruction = f"""作为任务规划者，你需要将用户输入解析成以下 JSON 格式的多个任务: 
{_output_format}

请注意，所有任务执行过程中都只能使用kubectl命令行。不要单独规划编写配置文件的步骤，而将配置文件放到kubectl命令里面。

对于每个task，你需要在 "id" 字段中以"task_正整数"的形式为其分配一个单独的task ID，并在 "description" 字段中详细地描述task内容，并在 "dep" 字段中写入该task需要完成的前置task ID 列表（如果没有前置task，则写入 []）。

请注意，每个task你都需要仔细思考原始用户输入中与该任务相关的信息，并**详细地**写入"description"字段中。参数值等信息不能省略，但不要写出完整的命令。

请严谨专业地一步步思考，综合考虑完成此任务所需的步骤。

# 注意: 拆分后的每个任务完成过程中都不能半途终止；

# 注意：**关注执行核心任务**，非必要时不需要确认信息是否正确、验证命令执行结果等。不要设置用户输入中未提到的配置项。

如果需要重新规划，你需要从completed_tasks.json中读取已完成的任务，从context.json中读取之前任务完成过程中的上下文信息，从error.json中读取之前任务完成过程中的出现的error信息，一步步思考该在原先规划上如何修改，保证推进用户请求 (即总任务) 的完成。

注意，你应该保证已完成任务（内容保持**完全相同**）出现在你修改后的任务规划中，并且保证新任务规划执行过程中能避免或修复error.json中的错误。
"""

_tools = []

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