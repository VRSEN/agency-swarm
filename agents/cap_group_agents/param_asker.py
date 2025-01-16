from agency_swarm import Agent
from agents.tools.read_context_index.ReadContextIndex import ReadContextIndex
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.tools.ask_user.AskUser import AskUser

_name = "param_asker"

_description = """
职责是查找参数值
"""
_input_format = """
{
    "unknown_param_1": {
        "name": ...,
        "description": ...,
        "type": ...
    },
    ...
}
"""

_output_format = """
{
    "param_1": {
        "name": ...,
        "value": ...
    },
    ...
}
其中，"name"字段是参数名称，"value"字段是对应参数值。
"""

_instruction = f"""
作为参数查询者，你将接收到一个未知参数列表，输入格式为:
{_input_format}
其中列出了所有未知参数的详细信息，包括参数名、参数描述和参数类型

你需要通过`ReadContextIndex`中读取已有环境中的上下文信息，`ReadContextIndex`的返回格式如下:
{{
    "index_1": {{
        "task_information": ...,
        "context_file_path": ...
    }},
    ...
}}
其中，"task_information"描述了和这条上下文信息相关的任务信息，"context_file_path"描述了这条上下文信息存储的路径
对于每个未知参数，你需要一步步思考，先对读取的index根据"task_information"和该参数的**相关性**由大到小进行排序；
然后使用`ReadJsonFile`读取"context_file_path"描述路径下的json文件，在返回结果中查找是否有该未知参数的值；
如果没有，选择下一个index重复上述步骤。如果所有的context中都没有该参数的值，你需要使用`AskUser`用以下格式向用户询问该参数的值:
{_input_format}

如果用户返回值仍有缺失，请继续使用`AskUser`用以上json格式向用户询问

最后，当你获得到所有未知参数值时，你应该用以下json格式返回结果:
{_output_format}
"""


_tools = [ReadContextIndex, ReadJsonFile, AskUser]

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