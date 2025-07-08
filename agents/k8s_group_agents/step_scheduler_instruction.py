def step_scheduler_instruction(_group_name, _input_format, _output_format):
    _instruction = f"""作为{_group_name}的调度者，你将收到一个 JSON 格式的step规划结果 <plan_graph> 和总任务描述 <main_task>。
输入格式为:
{_input_format}

同时，你需要先通过`ReadJsonFile`从completed_steps.json中读取已完成的step，从context_index.json中读取之前已完成的所有step的上下文信息。

获得以上信息后，你需要谨慎专业地一步步思考接下来应该执行的step，保证推进总任务的完成。选出下一步可执行的所有step，确保它们可以**并行执行**；如果两个step可以同时开始执行而彼此不冲突，则可以并行执行。

你应该以如下json格式输出调度结果: 
{_output_format}

你需要在"reason"字段填入你选出这些step的原因。
"""

    return _instruction