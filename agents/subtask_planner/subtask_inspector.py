from agency_swarm import Agent
_name = "subtask_inspector"

_description = """
职责是检查subtask_planner规划的任务是否合理
"""
_input_format = """
{
    "task_request": ...,
    "subtask_graph"{
        "subtask_1": {
            "title": 任务名称,
            "id": 任务ID, 
            "capability_group": <能力群名称>,
            "description": 任务描述, 
            "dep": <前置任务ID列表>,
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
作为审查者，你将从subtask_planner那里收到一个 JSON 格式的任务规划结果 <subtask_graph> 和原始任务请求 <task_request>。
输入格式为:
{_input_format}

请一步步思考: 
0. 你需要确保发给你的任务规划结果 <subtask_graph> 是以上的 JSON 格式；
1. 你需要检查<task_request>是否可以分解为<subtask_graph>，且确保<subtask_graph>任务的拆分和执行顺序合理；
2. 确保<subtask_graph>中没有**不通过华为云API或ssh连接命令行指令或编写、运行脚本**实现的操作；
3. 确保用户隐私，环境中已经有华为云访问认证等认证信息，且已经被所需agent得知，确保任务规划中没有获取访问凭证等类似步骤；
4. 除非<task_request>有说明，否则任务执行环境最开始应该没有创建**任何资源**，确保任务所需资源已经在**前置任务**中创建；
5. 你需要保证任务规划中没有**多余**的确认或查询步骤；
6. 确保<subtask_graph>中每个子任务的执行能力群"capability_group"名称正确且合理，所有能力群名称和介绍如下：
    a. "操作系统管理能力群": 该操作系统管理能力群提供通过SSH远程连接ECS执行命令的能力；
    b. "弹性云服务器(ECS)管理能力群": ECS管理能力群提供全面的ECS实例管理功能，包括创建、删除、查询、修改、迁移、启动、停止、重启等核心操作，以及克隆、规格推荐、网卡和硬盘配置等扩展功能；
    c. "镜像管理能力群": 负责华为云镜像资源管理任务，包括：查询镜像列表，更新镜像信息，制作镜像，镜像文件快速导入，使用外部镜像文件制作数据镜像，制作整机镜像，注册镜像，导出镜像，查询镜像支持的OS列表。
    d. "VPC网络管理能力群": VPC网络管理能力群提供对虚拟私有云（VPC）的管理功能，包括创建、删除和修改VPC；创建、删除和修改子网；配置安全组规则，控制网络流量；
    e. "云硬盘EVS管理能力群": EVS管理能力群提供对云硬盘的全面管理，包括创建、删除、查询、更新、扩容和配置QoS等云硬盘管理功能，以及创建、删除、更新和查询云硬盘快照的快照管理功能；
    f. "云监控CES能力群": CES管理能力群提供对云监控服务的全面管理，包括监控数据管理、监控看板管理和指标描述查询等云资源监控能力，以及云事件监控管理和告警规则管理等事件告警能力。


你应该按照以下json格式评估TASK: 
{_output_format}

如果任务拆分和流程合理，请在"review"字段填入"YES"；如果任务流程有问题，请在"review"字段填入"NO"，并在"explain"字段填入你觉得不合理的原因

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