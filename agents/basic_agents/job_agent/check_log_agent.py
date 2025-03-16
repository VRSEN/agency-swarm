from agency_swarm import Agent

_name = "check_log_agent"

_description = """
check_log_agent负责判断日志文件是否包含错误信息
"""

import os

_instruction = """
你的职责是判断日志文件是否包含错误信息

你将接收到日志文件的内容，该日志文件记录了一个任务的执行结果

例如，如果该任务为创建一个vpc，对应的日志文件将会记录该vpc是否成功创建，如果成功创建，日志中还会包括vpc的详细信息

你需要一步步思考，谨慎判断该日志文件对应的任务是否成功

如果任务执行失败，你需要详细说明根据日志文件推理出来的失败原因和失败信息，并输出"该任务执行失败"；

如果任务执行成功，你需要输出"该任务执行成功"
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