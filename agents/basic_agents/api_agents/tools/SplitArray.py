from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import re
import hashlib
from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

class SplitArray(BaseTool):
    '''
    分割Array，再返回合并结果
    '''

    user_requirement: str = Field(..., description="用户需求")
    api_name: str = Field(..., description="调用的API名")
    parameter: str = Field(..., description="需要判断的参数名")
    id: int = Field(..., description="需要判断的参数编号")
    description: str = Field(..., description="需要判断的参数描述")

    def extract_and_validate_json(self, text):
        try:
            data = json.loads(text)
            if isinstance(data, list) or isinstance(data, dict) or isinstance(data, str):
                return data
            else:
                return None
        except json.JSONDecodeError:
            pattern = r"```(?:json\s*)?(.*?)```"
            try:
                match = re.search(pattern, text, flags=re.DOTALL)
                if match:
                    data = json.loads(match.group(1).strip())
                    return data
                else:
                    return None
            except (ValueError, json.JSONDecodeError):
                return None
        

    def run(self):
        message_obj = {
            "user_requirement": self.user_requirement,
            "parameter": self.parameter,
            "description": self.description
        }
        result = self.send_message_to_agent(recipient_agent_name="Array Spiltter", message=json.dumps(message_obj, ensure_ascii=False), parameter=self.parameter)
        result_json = self.extract_and_validate_json(result)
        print(f"list: {result_json}")
        param_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"id={self.id}")
        param_row = param_df.iloc[0]
        ref_table_id = param_row.loc["ref_table_id"]
        result_list = []
        for user_req in result_json:
            SelectParamTabletool = SelectParamTable(caller_tool=self, user_requirement=user_req, api_name=self.api_name, table_id=ref_table_id)
            one_result_str = SelectParamTabletool.run()
            one_result = json.loads(one_result_str)
            new_result_json = []
            for param in one_result:
                param["label"] = (param["label"] if "label" in param else []) + [hashlib.md5(user_req.encode()).hexdigest()]
                new_result_json.append(param)
            result_list += new_result_json
        return result_list