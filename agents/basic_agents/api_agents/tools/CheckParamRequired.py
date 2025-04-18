from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import re
import hashlib
from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
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
        typestring = typestring.lower()
        print(typestring)
        if typestring.find("array") != -1:
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
            try:
                result_json = json.loads(result)
                new_result_json = []
                if isinstance(result_json, list):
                    for param in result_json:
                        param["label"] = (param["label"] if "label" in param else []) + [hashlib.md5(param["user_requirement"].encode()).hexdigest()]
                        new_result_json.append(param)
                result = json.dumps(new_result_json, ensure_ascii=False, indent=4)
            except:
                return result
        elif typestring.find("object") != -1:
            param_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"id={self.id}")
            param_row = param_df.iloc[0]
            tableid = param_row.loc["ref_table_id"]
            SelectParamTabletool = SelectParamTable(caller_tool=self, user_requirement=self.user_requirement, api_name=self.api_name, table_id=tableid)
            result = SelectParamTabletool.run()
        else:
            result = "需要该参数"
        return result