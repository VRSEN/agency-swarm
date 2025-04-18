from agency_swarm import Agent
_name = "simulator"

_description = """
负责模拟环境信息
"""

_instruction = """
你负责环境信息的模拟，当你接受到用户请求时，你需要生成模拟信息，尽可能的真实

输入格式如下:
{
    "title": ...,
    "description": ...,
    "context": ...,
}

其中"title"字段是用户请求的名称，"description"字段是用户请求的具体描述，"context"字段是已有的环境信息

结合任务描述和已有的环境信息，一步步思考在完成用户请求中可能产生的环境信息，包括描述资源信息和动作，注意请尽可能具体，尽可能用自然语言描述，根据用户请求或已有环境信息填写；如果前面的信息中没有提到过，请填入尽可能合适的信息

你模拟的环境信息应该是以下JSON格式:
{
    "new_context": ...
}

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