# from pydantic import Field, field_validator
#
# from agency_swarm import BaseTool
#
# from agency_swarm.tools.genesis.util import get_modules
#
# available_tools = get_modules('agency_swarm.tools')
#
# print(available_tools)
#
# class ImportTool(BaseTool):
#     """
#     This tool imports an existing tool from agency swarm framework.
#     """
#     tool_name: str = Field(..., description=f"Name of the tool to be imported. Available tools are: {[item for sublist in available_tools.values() for item in sublist]}")
#
#     def run(self):
#         # find item in available_agents dict by value
#         import_path = [k for k, v in available_tools.items() if self.tool_name in v][0]
#
#         import_path = import_path.replace(f".{self.tool_name}", "")
#
#         return "To import the tool, please add the following code: \n\n" + \
#                f"from {import_path} import {self.tool_name}\n" + \
#                f"agent = {self.tool_name}()"
#
#     @field_validator("tool_name", mode='after')
#     @classmethod
#     def agent_name_exists(cls, v):
#         if v not in [item for sublist in available_tools.values() for item in sublist]:
#             raise ValueError(f"Tool with name {v} does not exist. Available tools are: {[item for sublist in available_tools.values() for item in sublist]}")
#         return v