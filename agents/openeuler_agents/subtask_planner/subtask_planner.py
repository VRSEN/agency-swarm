from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile

_name = "subtask_planner"

_description = """
职责是将任务按能力群拆分成子任务
"""

_input_format = """
{
    "title": <本次任务的名称>,
    "description": <本次任务的描述>,
    "total_task_graph": <所有任务的规划图>
}
"""

_output_format = """
{
    "subtask_1": {
        "title": 子任务名称,
        "id": 子任务ID, 
        "capability_group": <能力群名称>,
        "description": 子任务描述, 
        "dep": <前置子任务ID列表>
    },
    ...
}
"""

_instruction = f"""作为子任务规划者，你将接收到一个任务，并尝试一步步对该任务做规划。

输入格式如下: 
{_input_format}

其中，"title"和"description"字段描述了本次需要规划的task，"total_task_graph"将描述所有task的规划图，包括任务信息和依赖关系。你接下来对本task进行各个subtask的规划，**且不要与其它的task冲突或重复**。

同时，你需要先调用工具`ReadJsonFile`从context_tree.json中读取已经完成的所有任务过程的上下文信息。（直接调用工具，不要把它规划为一个subtask）
获取以上信息后，你还需要判断其中已经完成任务的api调用结果是否与本次规划有关，如果有关，请你用`ReadJsonFile`读取相应的api调用结果文件的内容（直接调用工具不要规划为一个step）后再进行规划

注意: 你每次接收到输入都需要读取一遍context_tree.json

你需要严谨专业地一步步思考，根据任务描述对该任务进行拆分。你需要确保:

1. 每一个子任务都由且只由一个能力群来完成；

2. 子任务不能偏离任务目的；

3. 子任务的内容不能与其他任何任务的内容有重复，避免过度规划。

现有的能力群名称和介绍如下: 


- "软件能力群": 负责软件包管理、代码仓库管理、软件配置优化（A-Tune工具）；
- "安全能力群": 负责漏洞扫描（secScanner工具）、漏洞修复（SysCare工具）；
- "操作系统能力群": 负责用户和文件等权限管理、网络及防火墙管理。
以上三个能力群为OpenEuler操作系统管理能力群，需要用到ssh命令连接至服务器；
注意：需要用到ssh命令的子任务请用以上三个能力群完成。


注意：下面的能力群只能调用api管理当前账户资源，无法使用命令连接到服务器
- "弹性云服务器(ECS)管理能力群": ECS管理能力群提供全面的ECS实例管理功能，包括创建、删除、查询、修改、迁移、启动、停止、重启等核心操作，以及克隆、规格推荐、网卡和硬盘配置等扩展功能；
- "镜像管理能力群": 负责华为云镜像资源管理任务，包括：查询镜像列表，更新镜像信息，制作镜像，镜像文件快速导入，使用外部镜像文件制作数据镜像，制作整机镜像，注册镜像，导出镜像，查询镜像支持的OS列表。
- "VPC网络管理能力群": VPC网络管理能力群提供对虚拟私有云（VPC）的管理功能，包括创建、删除和修改VPC；创建、删除和修改子网；配置安全组规则，控制网络流量；
- "集群管理能力群": 集群管理能力群提供对华为云k8s集群（即CCE）的管理功能，包括创建、删除、查询、更新、休眠、唤醒、添加集群标签等核心操作，以及更改集群规格等扩展功能；
- "节点管理能力群": 节点管理能力群提供对CCE节点的管理功能，包括创建、删除、查询、更新等操作，以及节点池的管理和控制节点缩容保护。
以上五个能力群为华为云资源管理能力群，需要调用api管理当前账户的资源

- "综合能力群": 负责进行结构化分析汇总和文本结构化输出等文本相关任务

你必须严格按照以下json格式输出子任务规划结果:
{_output_format}

对于每个subtask，你需要在 "id" 字段中以"subtask_正整数"的形式为其分配一个单独的subtask ID，并在"capability_group"字段填入完成该subtask所需的能力群名称，并在 "description" 字段中描述subtask内容，并在 "dep" 字段中写入该subtask依赖的前置subtask ID 列表（如果没有前置subtask，则写入 []）。

请注意，每个subtask你都需要仔细思考任务描述中与该子任务相关的信息，并**详细地**写入"description"字段中。参数值等信息不能省略，但不要写出完整的命令。

请逐步思考，综合考虑完成此任务所需的子任务。

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