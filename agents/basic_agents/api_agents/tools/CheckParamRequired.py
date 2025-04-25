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

    def extract_and_validate_json(self, text):
        """
        判断字符串是否能转成 JSON，并提取 ```json 块中的 JSON 内容。

        Args:
            text: 输入的字符串。

        Returns:
            如果整个字符串是有效的 JSON，则返回解析后的 JSON 对象。
            如果字符串中包含 ```json 块，则返回解析后的块中的 JSON 对象。
            如果无法解析为 JSON，则返回 None。
        """
        try:
            # 尝试将整个字符串解析为 JSON
            text = re.sub(r"\s*'([^']*)'", r'"\1"', text)
            result_json = json.loads(text)
            return result_json
        except json.JSONDecodeError:
            # 如果整个字符串不是 JSON，尝试查找 ```json 块
            json_blocks = re.findall(r"```json\s*([\s\S]*?)\s*```", text)
            if json_blocks:
                # 如果找到 ```json 块，尝试解析第一个块中的内容
                try:
                    result_json = json.loads(json_blocks[0])
                    return result_json
                except json.JSONDecodeError:
                    return None  # ```json 块中的内容也不是有效的 JSON
            else:
                return None  # 字符串中既不是完整的 JSON，也没有 ```json 块
        

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
            print(f"Array result: {result}")
            result_json = self.extract_and_validate_json(result)
            print(f"Array: {result_json}")
            if isinstance(result_json, list):
                result = json.dumps(result_json, ensure_ascii=False, indent=4)
        elif typestring.find("object") != -1:
            param_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"id={self.id}")
            param_row = param_df.iloc[0]
            tableid = param_row.loc["ref_table_id"]
            SelectParamTabletool = SelectParamTable(caller_tool=self, user_requirement=self.user_requirement, api_name=self.api_name, table_id=tableid)
            result = SelectParamTabletool.run()
        else:
            result = "需要该参数"
        return result