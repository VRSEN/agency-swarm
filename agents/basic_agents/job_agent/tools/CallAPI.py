from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os
from agents.basic_agents.job_agent.tools.CheckLogForFailures import CheckLogForFailures
from agents.basic_agents.api_agents.tools.FillAndCallAPI import FillAndCallAPI

class CallAPI(BaseTool):
    '''填写api和调用api'''
    param_list: list = Field(..., description="调用API所需的参数列表，其中每一项需要包括\"parameter\", \"id\", \"description\", \"label\"(如果有), \"type\", \"value\"")
    api_name: str = Field(..., description="需要调用的API名称")

    def run(self):
        # api Filler
        # api Caller
        print(self.param_list)
        FillAndCallAPItool = FillAndCallAPI(caller_tool=self, param_list=self.param_list, api_name=self.api_name)
        read_file_path = FillAndCallAPItool.run()
        # CheckLogForFailures: 判断文件中是否有失败信息
        
        CheckLogForFailurestool = CheckLogForFailures(caller_tool=self, read_file_path=read_file_path)
        result = CheckLogForFailurestool.run()
        return result 
  