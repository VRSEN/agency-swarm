from agency_swarm import Agent

_name = "param_asker"

_description = """
职责是查找参数值
"""
_input_format = """
{
    "user_requirement": ...,
    "param_list": [{
        "parameter": ...,
        "id": ...,
        "description": ...,
        "label": [...],
        "type": ...
    }, ...]
}
"""

_output_format = """
[{
    "parameter": ...,
    "id": ...,
    "description": ...,
    "label": [...],
    "type": ...,
    "value": ...
}, ...]
"""

_instruction = f"""
作为参数查询者，你将接收到一个未知参数列表，输入格式为:
{_input_format}
其中"user_requirement"为用户需求，"param_list"列出了所有未知参数的详细信息，包括参数名、参数编号、参数描述、参数标识列表和参数类型

请一步步思考，逐步进行下述操作：

对于每个未知参数，你需要仔细而谨慎地思考，考虑"user_requirement"中哪里可以获取到该参数的值

# 注意: 当你认为可以从"user_requirement"中获取到该参数的值时，你需要考虑如果该参数为这个值是否**完全符合**该参数的description和type，如果符合，才可以认为该参数为这个值

最后，当你获得到所有未知参数值时，你应该用以下列表格式返回结果:
{_output_format}

例如，如果有参数a和b需要返回，参数信息分别为：
{{
    "parameter": "a",
    "id": 5,
    "description": "Example parameter 1",
    "label": ["a1", "a2"],
    "type": "String",
    "value": "QAQ"
}},

{{
    "parameter": "b",
    "id": 17,
    "description": "Example parameter 2",
    "label": ["b1"],
    "type": "Intger",
    "value": 123
}}
    
则你应该返回:[{{
    "parameter": "a",
    "id": 5,
    "description": "Example parameter 1",
    "label": ["a1", "a2"],
    "type": "String",
    "value": "QAQ"
}},{{
    "parameter": "b",
    "id": 17,
    "description": "Example parameter 2",
    "label": ["b1"],
    "type": "Intger",
    "value": 123
}}]

其中，"parameter"字段是参数名称，"value"字段是对应参数值。
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
