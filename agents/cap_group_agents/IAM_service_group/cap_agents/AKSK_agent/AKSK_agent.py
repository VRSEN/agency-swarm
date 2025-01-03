from agency_swarm import Agent

_name = "AKSK_agent"

_description = """
职责是获取华为云账户AKSK
"""
_input_format = """
"""

_output_format = """
"""

_instruction = "./instructions.md"

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