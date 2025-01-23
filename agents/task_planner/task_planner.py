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
        "dep": <前置任务ID列表>,
    },
    ...
}
"""

_instruction = """
无论用户输入什么，你都应该直接输出以下内容:
{
    "task_1": {
        "title": "选择ECS规格",
        "id": "task_1",
        "description": "选择一个适用于ECS实例的规格，调用华为云API获取可用的ECS规
格列表，并选择一个规格（例如：'s3.medium.1'）。",
        "dep": []
    },
    "task_2": {
        "title": "创建虚拟私有云（VPC）及子网",
        "id": "task_2",
        "description": "调用华为云API创建一个新的虚拟私有云（VPC）及其子网，指定 
可用区为'cn-north-4a'。",
        "dep": []
    },
    "task_3": {
        "title": "创建安全组",
        "id": "task_3",
        "description": "在创建VPC的同时，调用华为云API创建一个安全组，为ECS实例配
置安全规则。",
        "dep": ["task_2"]
    },
    "task_4": {
        "title": "创建ECS实例",
        "id": "task_4",
        "description": "调用华为云API在'cn-north-4a'可用区创建一个ECS实例，使用选
定的规格、创建的VPC、子网和安全组。",
        "dep": ["task_1", "task_3"]
    }
}
"""

f"""
作为任务规划者，你需要将用户输入解析成以下 JSON 格式的多个任务: 
{_output_format}

请逐步思考，用户可能会提供修改建议，综合考虑完成此任务所需的步骤。
# 注意: 拆分后的每个任务完成过程中都不能半途终止；
# 注意: 用户输入的所有信息都是默认无误的，你不需要规划出有确认信息是否正确的步骤；
# 注意: 初始环境中资源都是充足的，你不需要对可用区资源是否足以执行任务进行查询；
# 注意: 除非用户请求中有提供初始条件的描述，初始环境中除了华为云账号和可用的华为云访问凭证，没有创建**任何资源**；确保你的规划有你任务中**所需资源的创建**或**所需信息的获取**步骤，否则请先完成它们；
# 注意: 为了防止用户隐私不被泄露，华为云认证信息已被执行任务的agent得知，你的任务规划中不需要获取华为云访问凭证等认证信息

如果需要重新规划，你需要从completed_tasks.json中读取已完成的任务，从context.json中读取之前任务完成过程中的上下文信息，从error.json中读取之前任务完成过程中的出现的error信息，一步步思考该在原先规划上如何修改，保证推进用户请求 (即总任务) 的完成
注意，你应该保证**已完成任务（内容不应该有任何修改）**出现在你修改后的任务规划中，并且保证新任务规划执行过程中能避免或修复error.json中的Error

对于每个任务，你需要在 "id" 字段中以"task_正整数"的形式为其分配一个单独的任务 ID，并在 "description" 字段中详细地描述任务内容，并在 "dep" 字段中写入该任务需要完成的前置任务 ID 列表（如果没有前置任务，则写入 []），允许环的构建，表示这些任务需要多次迭代执行。
确保你的任务规划尽可能并行。如果两个任务可以同时开始执行而彼此不冲突，则可以并行执行。
请注意，无论任务是什么，任务执行过程中都只能通过调用api或ssh远程命令行连接或编写、运行脚本进行操作。
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