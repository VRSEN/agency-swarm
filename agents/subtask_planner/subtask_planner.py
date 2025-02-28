from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.tools.read_context_index.ReadContextIndex import ReadContextIndex

_name = "subtask_planner"

_description = """
职责是将任务按能力群拆分成子任务
"""

_input_format = """
{
    "total_task_graph": <所有任务规划图>
    "title": <任务名称>,
    "description": <任务描述>,
}
"""

_output_format = """
{
    "subtask_1": {
        "title": 任务名称,
        "id": 任务ID, 
        "capability_group": <能力群名称>,
        "description": 任务描述, 
        "dep": <前置任务ID列表>,
    },
    ...
}
"""

_instruction = f"""
作为子任务规划者，你将接收到一个任务，并尝试一步步对该任务做规划

输入格式如下: 
{_input_format}

其中，"title"和"description"字段描述了本次需要规划的任务，"total_subtask_graph"将描述所有任务的规划图，包括任务信息和依赖关系，保证你接下来的规划不要与其他任务冲突或重叠

同时，你需要从context_index.json中读取并更新你记忆中的已有环境中的上下文信息
注意: 你每次接收到输入都需要读取一遍context_index.json

你需要一步步思考，根据任务描述对该任务进行拆分，你需要确保:
1. 每一个子任务都由且只由一个能力群来完成；
2. 子任务不能偏离任务目的

现有的能力群名称和介绍如下: 
"操作系统管理能力群": 该操作系统管理能力群提供通过SSH远程连接ECS执行命令的能力；
"弹性云服务器(ECS)管理能力群": ECS管理能力群提供全面的ECS实例管理功能，包括创建、删除、查询、修改、迁移、启动、停止、重启等核心操作，以及克隆、规格推荐、网卡和硬盘配置等扩展功能；
"镜像管理能力群": 负责华为云镜像资源管理任务，包括：查询镜像列表，更新镜像信息，制作镜像，镜像文件快速导入，使用外部镜像文件制作数据镜像，制作整机镜像，注册镜像，导出镜像，查询镜像支持的OS列表。
"VPC网络管理能力群": VPC网络管理能力群提供对虚拟私有云（VPC）的管理功能，包括创建、删除和修改VPC；创建、删除和修改子网；配置安全组规则，控制网络流量；
"云硬盘EVS管理能力群": EVS管理能力群提供对云硬盘的全面管理，包括创建、删除、查询、更新、扩容和配置QoS等云硬盘管理功能，以及创建、删除、更新和查询云硬盘快照的快照管理功能；
"云监控CES能力群": CES管理能力群提供对云监控服务的全面管理，包括监控数据管理、监控看板管理和指标描述查询等云资源监控能力，以及云事件监控管理和告警规则管理等事件告警能力。
"集群管理能力群": 集群管理能力群提供对华为云k8s集群（即CCE）的管理功能，包括创建、删除、查询、更新、休眠、唤醒、添加集群标签等核心操作，以及更改集群规格等扩展功能；
"节点管理能力群": 节点管理能力群提供对CCE节点的管理功能，包括创建、删除、查询、更新等操作，以及节点池的管理和控制节点缩容保护。
"简单任务处理能力群": 负责简单任务（即不需要执行操作）的处理，如做出选择或决定

你应该用以下json格式做子任务规划:
{_output_format}

请逐步思考，用户可能会提供修改建议，综合考虑完成此任务所需的步骤。
# 注意: 拆分后的每个任务完成过程中都不能半途终止；
# 注意：每个subtask的"dep"字段中填入的id必须是当前这次输出中的规划中存在的subtask
# 注意: 初始环境中资源都是充足的，你不需要对可用区资源是否足以执行任务进行查询；
# 注意: 用户输入和context.json的所有信息都是默认无误的，你不需要规划出有确认信息是否正确的步骤；
# 注意: 除非用户请求中或context的上下文信息中有提供环境条件的描述，初始环境中没有创建**任何资源**，且不提供任何**资源和环境信息**；确保你的规划有你任务中**所需资源的创建**或**所需信息的获取**的步骤，否则请先完成它们；
# 注意: 为了防止用户隐私不被泄露，华为云认证信息已被执行任务的agent得知，你的任务规划中不需要获取华为云访问凭证等认证信息

对于每个子任务，你需要在 "id" 字段中以"subtask_正整数"的形式为其分配一个单独的子任务ID，并在"capability_group"字段填入完成该子任务所需的能力群名称，并在 "description" 字段中描述任务内容，并在 "dep" 字段中写入该子任务需要完成的前置子任务 ID 列表（如果没有前置任务，则写入 []），允许环的构建，表示这些子任务需要多次迭代执行。
确保你的规划结果应该尽可能可以并行执行。如果两个子任务可以同时开始执行而彼此不冲突，则可以并行执行。
请注意，无论子任务是什么，子任务执行过程中都只能通过调用api或ssh远程命令行连接或编写、运行脚本进行操作。
"""


_tools = [ReadJsonFile, ReadContextIndex]

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