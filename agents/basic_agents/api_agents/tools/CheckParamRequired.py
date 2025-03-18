from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import re
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

class CheckParamRequired(BaseTool):
    '''
    判断参数类型
    '''

    user_requirement: str = Field(..., description="用户需求")
    api_name: str = Field(..., description="调用的API名")
    parameter: str = Field(..., description="需要判断的参数名")
    id: int = Field(..., description="需要判断的参数编号")
    description: str = Field(..., description="需要判断的参数描述")
    # parents_description: dict = Field(..., description="需要判断的参数的前置参数描述，如果没有前置参数请填入\{\}")
    type: str = Field(..., description="需要判断的参数类型")
    mandatory: int = Field(..., description="该参数是否必需")

    def run(self):
        typestring = self.type
        print(typestring)
        if typestring.find("Array") != -1:
            message_obj = {
                "user_requirement": self.user_requirement,
                "api_name": self.api_name,
                "parameter": self.parameter,
                "id": self.id,
                "description": self.description,
                # "parents_description": self.parents_description,
                "type": typestring,
                "mandatory": self.mandatory
            }
            result = self.send_message_to_agent(recipient_agent_name="Array Selector", message=json.dumps(message_obj, ensure_ascii=False), parameter=self.parameter)
        elif typestring.find("object") != -1:
            tableids = re.findall(r'见表\d+', self.description)
            tableid = re.findall(r'\d+', tableids[0])
            SelectParamTabletool = SelectParamTable(caller_tool=self, user_requirement=self.user_requirement, api_name=self.api_name, table_id=tableid[0])
            result = SelectParamTabletool.run()
        else:
            result = "需要该参数"
        return result