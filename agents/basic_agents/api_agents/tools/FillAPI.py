from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.utils import try_parse_json

from agents.basic_agents.api_agents.tools.FillParamTable import FillParamTable

class FillAPI(BaseTool):
    '''
    根据用户需求，填写并返回一个 API 的所有参数值。
    '''

    api_name: str = Field(..., description="目标API名")
    user_requirement: str = Field(..., description="用户需求")

    def fill_uri_parameter(self, row):
        # 1. construct the message
        message_obj = {
            "user_requirement": self.user_requirement,
            "api_name": self.api_name,
            "parameter": row["parameter"],
            "description": row["description"],
            "mandatory": row["mandatory"],
        }
        if row["type"] is not None:
            message_obj["type"] = row["type"]
        
        # 2. send the message and handle response
        value_str = self.send_message_to_agent(recipient_agent_name="Param Filler", message=json.dumps(message_obj, ensure_ascii=False))

        if "不需要该参数" in value_str:
            return None, None
        else:
            return row["parameter"], try_parse_json(value_str)

    def run(self):
        debug_parallel = os.getenv("DEBUG_API_AGENTS_PARALLEL")

        # 1. get general information about this API
        apis_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='apis', condition=f'name=\'{self.api_name}\'')
        assert len(apis_df) == 1, f"API '{self.api_name}' does not exist or has duplicates."
        api_row = apis_df.iloc[0]
        method = api_row.loc["method"]
        uri = api_row.loc["uri"]
        api_id = api_row.loc["id"]
        root_table_id = api_row.loc["root_table_id"]

        # 2. for each URI parameter, call Param Filler to decide its value
        uri_parameters_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='uri_parameters', condition=f'api_id=\'{api_id}\'')
        uri_param_values = {}

        if debug_parallel is not None and debug_parallel.lower() == "true":
            for _, row in uri_parameters_df.iterrows():
                key, value = self.fill_uri_parameter(row)
                if value is not None:
                    uri_param_values[key] = value

        else:
            with ThreadPoolExecutor() as executor:
                futures = []
                for _, row in uri_parameters_df.iterrows():
                    futures.append(executor.submit(self.fill_uri_parameter, row))
                for future in as_completed(futures):
                    key, value = future.result()
                    if value is not None:
                        uri_param_values[key] = value

        # 3. Call FillParamTable() to decide the value of all request parameters
        fill_param_table_instance = FillParamTable(caller_tool = self,
                                                   user_requirement=self.user_requirement,
                                                   api_name=self.api_name,
                                                   table_id=root_table_id)
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
