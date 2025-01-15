def manager_instruction(_group_name, _superior_agent):
    _input_format = """
    {
        "result": "QUERY",
        "context": {
            "user_request": ...
            "param_1": {
                "name": ...,
                "description": ...,
                "type": ...
            },
            ...
        }
    }
    其中，"user_request"是用户初始请求，"name"字段是所需参数名称，"description"字段是所需参数描述，"type"字段是所需参数类型。
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
    你是{_group_name}的消息管理者，你需要接收、处理、转发来自{_group_name}中的能力agent或{_superior_agent}的消息。
    输入消息格式如下:
    {_input_format}
    你需要一步步思考，对于输入中列出的每个所需参数，你都需要思考这个参数的值是否可以从<user_request>中获得；
    对于所有无法从用户初始请求中获得值的参数，你需要通过`SendMessage`用以下json格式将这些参数发送给param_asker:
    {{
        "unknown_param_1": {{
            "name": ...,
            "description": ...,
            "type": ...
        }},
        ...
    }}
    在接收到param_asker的结果后，你需要将上述所有参数用以下json格式返回:
    {_output_format}
    其中，你应该在"value"字段填入参数值，这些参数值来自于上述过程中的用户初始请求或者param_asker的返回结果。
    """

    return _instruction