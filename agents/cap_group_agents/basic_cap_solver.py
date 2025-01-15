from agency_swarm import Agent
from agents.tools.read_json_file.ReadJsonFile import ReadJsonFile
from agents.tools.ask_user.AskUser import AskUser
from agents.tools.read_context_index.ReadContextIndex import ReadContextIndex
from agents.tools.create_context.CreateContext import CreateContext

_name = "basic_cap_solver"

_description = """
职责是处理简单任务
"""
_input_format = """
{
    "user_request": <用户请求>,
    "title": <当前任务名称>,
    "description": <当前任务描述>,
}
"""

_output_format = """
{
    "result": "SUCCESS",
    "context": <记录决定或选择信息文件的路径>
}
"""

_instruction = f"""
作为简单任务执行者，你将接收到一个简单任务，输入格式为:
{_input_format}

你需要通过`ReadContextIndex`中读取已有环境中的上下文信息，`ReadContextIndex`的返回格式如下:
{{
    "index_1": {{
        "task_information": ...,
        "context_file_path": ...
    }},
    ...
}}

其中，"task_information"描述了和这条上下文信息相关的任务信息，"context_file_path"描述了这条上下文信息存储的路径
你需要一步步思考，先对读取的index根据"task_information"和当前任务的**相关性**由大到小进行排序；
然后使用`ReadJsonFile`读取"context_file_path"描述路径下的json文件，得到该上下文信息；
如果当前信息充足，你需要解决你接收到的简单任务（任务内容可能是做出决定或选择）；
如果你还需要更多相关信息，选择下一个index重复上述步骤。

当你做出决定或选择时，你需要通过`AskUser`向用户征求意见，
如果用户不同意你的决定或选择，你可以结合用户返回的意见，通过AskUser继续提出新的决定或选择
如果用户同意你的决定或选择，你需要使用`CreateContext`将你的决定或选择用自然语言写入一个新文件中，将返回该新文件路径

最后，你应该用以下格式返回:
{_output_format}
其中，"context"字段应该写入你创建的记录决定或选择的新文件路径
"""


_tools = [ReadJsonFile, AskUser, CreateContext, ReadContextIndex]

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