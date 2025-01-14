def manager_instruction(_group_name, _superior_agent):
    _instruction = f"""
    你是{_group_name}的消息管理者，你需要接收、处理、转发来自{_group_name}中的能力agent或{_superior_agent}的消息。

    当你接收到消息时，一步步思考，你需要根据消息发送者和消息内容来选择下一步操作：
    1. 如果消息是{_group_name}中的能力agent询问参数信息，你需要
    """

    return _instruction