from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
# from agents.tools.read_context_index.ReadContextIndex import ReadContextIndex

_name = "subtask_planner"

_description = """
职责是将任务按能力群拆分成子任务
"""

_input_format = """
{
    "title": <任务名称>,
    "description": <任务描述>,
    "total_task_graph": <所有任务规划图>,
}
"""

_output_format = """
{
    "subtask_1": {
        "title": 任务名称,
        "id": 任务ID, 
        "capability_group": <能力群名称>,
        "description": 任务描述, 
        "dep": <前置任务ID列表>
    },
    ...
}
"""

_instruction = f"""作为子任务规划者，你将接收到一个任务，并尝试一步步对该任务做规划。

输入格式如下: 
{_input_format}

其中，"title"和"description"字段描述了本次需要规划的task，"total_task_graph"将描述所有task的规划图，包括任务信息和依赖关系。你接下来对本task中各个subtask的规划，且不要与其它的task冲突或重叠。

# 规划开始之前，你需要判断用户输入请求是否与文字输出有关（例如：输出复盘报告、输出预案、输出自动化脚本等），如果有关，你需要将用户输入请求中的相关信息传递给监控能力群中的文本输出agent来进行输出（只有这一个subtask），不需要规划其他任何多余的subtask。

同时，你需要先调用工具`ReadJsonFile`从completed_sub_tasks.json读取已完成的子任务，从context.json中读取已经完成的所有过程的上下文信息。（直接调用工具，不要把它规划为一个subtask）
获取以上信息后，你需要判断用户输入请求是否与之前已完成的过程有关，如果有关，从上下文信息中提取有用信息，并结合该信息进行后续的任务规划。

你需要严谨专业地一步步思考，根据任务描述对该任务进行拆分。你需要确保:

1. 每一个子任务都由且只由一个能力群来完成；

2. 子任务不能偏离任务目的；

3. 子任务的内容不能与已经完成的子任务或已经完成的步骤有重复，要尽可能避免过度规划。

4. 子任务执行过程中如果需要使用kubectl命令行，不要单独规划编写配置文件的步骤，而将配置文件放到kubectl命令里面。

现有的能力群名称和介绍如下: 

- "pod管理能力群": 负责pod管理、资源分组（Label管理、Namespace管理）
- "pod编排调度能力群": 负责无状态负载管理、有状态负载管理、任务管理、守护进程集管理、亲和和反亲和调度
- "配置管理能力群": 负责环境配置管理、隐私管理
- "存储能力群": 负责磁盘管理、PV管理、PVC管理、StorageClass管理、CSI管理
- "监控能力群": 负责云原生配置、云原生观测、弹性策略管理、文本输出
- "软件管理能力群": 负责软件安装、修改软件配置、软件监控


你应该用以下json格式输出子任务规划:
{_output_format}

对于每个subtask，你需要在 "id" 字段中以"subtask_正整数"的形式为其分配一个单独的subtask ID，并在"capability_group"字段填入完成该subtask所需的能力群名称，并在 "description" 字段中描述subtask内容，并在 "dep" 字段中写入该subtask依赖的前置subtask ID 列表（如果没有前置subtask，则写入 []）。

请注意，每个subtask你都需要仔细思考任务描述中与该子任务相关的信息，并**详细地**写入"description"字段中。参数值等信息不能省略，但不要写出完整的命令。

请逐步思考，综合考虑完成此任务所需的步骤。

# 注意：每个subtask的"dep"字段中填入的id必须是当前这次输出的规划中存在的subtask；

# 注意：**关注执行核心任务**，非必要时不需要确认信息是否正确、验证命令执行结果等。不要设置用户输入中未提到的配置项。
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