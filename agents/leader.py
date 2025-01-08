from agency_swarm import Agent
_name = "leader"

_description = """
Responsible for forwarding user requests
"""

_instruction = """
你需要接收用户请求并将其作为任务发送给"task_planner"。
当你收到"task_planner"的返回结果时，你需要将结果中JSON格式的部分和原始请求以以下JSON格式发送给"inspector"：
{
    "answer": <结果中JSON格式的部分>, 
    "user_request": 原始请求
}
例如，如果"task_planner"返回的结果中JSON格式的部分是：
{
    "task1": {...},
    "task2": {...},
    ...
}
你应该发送的JSON是：
{
    "answer": {
        "task1": {...},
        "task2": {...},
        ...
    },
    "user_request": ...
}

# 确保你要发送的JSON包含"answer"字段和"user_request"字段。
如果"inspector"返回的决定是"no"，根据"inspector"返回的"reason"部分判断，如果是缺失了信息，首先检查你发送的JSON是否符合上述要求，如果有问题，补全JSON重新发送给"inspector"；否则将原始用户请求和"inspector"返回的"reason"部分发送给"task_planner"。
如果"inspector"返回的决定是"yes"，则将"task_planner"的结果中JSON格式的部分发送给用户
"""


"""
You need to receive user requests and send them to "task_planner" in the form of tasks.
When you receive the return result of "task_planner", you need to send the returned the JSON formatted part of the result and the original request to "inspector" in the following JSON format:
{
    "answer": <the JSON formatted part of the result>, 
    "user_request": original_request
}.
For example, if "task_planner" returns the JSON formatted part of the result is:
{
    "task1": {...},
    "task2": {...},
    ...
}
The JSON You should sent is:
{
    "answer": {
        "task1": {...},
        "task2": {...},
        ...
    },
    "user_request": ...
}

Ensure that the JSON you want to send contains the "answer" field and "user_request" field.
If the "inspector" returns a decision of "no", then send the original user request and the "reason" section returned by the "inspector" to the "task_planner".


"""
#If the "inspector" returns a decision of "yes", then send each sub-task individually to the "capability_planner".

#When you receive the return result of "capability_planner", you need to send the returned JSON format result to "inspector_capability".

#If the "inspector_capability" returns a decision of "no", then send the "reason" section returned by the "inspector_capability" to the "capability_planner".


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
                 max_prompt_tokens=25000,)