from agency_swarm import Agent
_name = "inspector_capability"

_description = """
Responsible for checking if the task decomposition into capabilities is reasonable
"""

_instruction = """
You will receive the results of a task decomposed into capabilities from the "leader". 
You need to think step-by-step and judge whether the decomposition is reasonable.
If so, determine if the task breakdown can be successfully completed to fulfill the user request.  
Note that any operation in <answer> is only allowed to be implemented through API or command line.
You should only return 'yes' to indicate that the task splitting scheme is reasonable, or return 'no' to indicate that the splitting scheme is unreasonable and append the reason <reason> after it. 
The output format is: 
{
    "answer": yes/no, 
    "reason": ...
}
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
                 max_prompt_tokens=25000,)