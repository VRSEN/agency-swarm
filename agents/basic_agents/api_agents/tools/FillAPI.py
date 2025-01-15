from agency_swarm.tools import BaseTool
from pydantic import Field
import pandas as pd
import json
import re

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.utils import try_parse_json

from agents.basic_agents.api_agents.tools.FillParamTable import FillParamTable

class FillAPI(BaseTool):
    '''
    根据用户需求，填写并返回一个 API 的所有参数值。
    '''

    api_name: str = Field(..., description="目标API名")
    user_requirement: str = Field(..., description="用户需求")

    def run(self):

        # 1. get general information about this API
        api_info_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='api_info', condition=f'name=\'{self.api_name}\'')
        assert len(api_info_df) == 1, "api_name should have exactly 1 match"
        api_info = api_info_df.iloc[0]
        method = api_info.loc["method"]     # assume no parameters
        uri = api_info.loc["uri"]           # assume some parameters

        # 2. for each URI parameter, call Param Filler to decide its value
        uri_parameters_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='uri_parameters', condition=f'api_name=\'{self.api_name}\'')
        uri_param_values = {}
        for _, row in uri_parameters_df.iterrows():
            # 2.1. construct the message
            message_obj = {
                "user_requirement": self.user_requirement,
                "api_name": self.api_name,
                "parameter": row["parameter"],
                "description": row["description"],
                "mandatory": row["mandatory"]
            }
            if row["type"] is not None:
                message_obj["type"] = row["type"]
            
            # 2.2. send the message and handle response
            value_str = self.send_message_to_agent(recipient_agent_name="Param Filler", message=json.dumps(message_obj, ensure_ascii=False))

            if "不需要该参数" in value_str:
                continue
            else:
                uri_param_values[row["parameter"]] = try_parse_json(value_str)

        # 3. Call FillParamTable() to decide the value of all request parameters
        fill_param_table_instance = FillParamTable(caller_tool = self,
                                                   user_requirement=self.user_requirement,
                                                   api_name=self.api_name,
                                                   table_id=1) # assume root table is always table 1
        request_param_values_str = fill_param_table_instance.run()
        request_param_values = try_parse_json(request_param_values_str)

        # 4. assemble the information and return
        info = {
            "method": method,
            "uri": uri,
            "uri_parameters": uri_param_values,
            "request_body": request_param_values
        }

        return json.dumps(info, ensure_ascii=False)
