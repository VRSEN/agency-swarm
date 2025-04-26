def step_scheduler_instruction(_group_name, _input_format, _output_format):
    # TODO: 改instructions
    _instruction = f"""
    作为{_group_name}调度者，你将接收到step流程和初始用户请求，输入格式如下:  
    你将从task_planner那里收到一个 JSON 格式的step规划结果 <plan_graph> 和总任务描述 <main_task>。
    输入格式为:
    {_input_format}

    你需要先从completed_steps.json中读取并更新你记忆中的已完成的step，从context_index.json中读取之前step完成过程中的上下文信息，并结合总任务描述一步步思考接下来需要完成的step，保证推进总任务的完成
    
    注意: 你每次接收到输入时都应该读取一次completed_steps.json和context_index.json

    你需要根据已完成step和上下文信息选出下一步可执行的所有step，确保它们可以**并行执行**；如果两个step可以同时开始执行而彼此不冲突，则可以并行执行。

    你的最终调度结果应该为: 
    {_output_format}

    你需要在"reason"字段填入你选出这些step的原因
    """

    return _instruction