from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.utils import try_parse_json, assert_list_of_dicts

from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

class SelectAPIParam(BaseTool):
    '''
    根据用户需求，选择一个 API 的所有需要填写的参数字段，包括必选参数、用户选择的可选参数和环境参数。
    '''

    api_name: str = Field(..., description="目标API名")
    user_requirement: str = Field(..., description="自然语言的用户需求")

    def select_uri_parameter(self, row):
        returned_keys = ["parameter", "description", "type"]
        returned_info = {key: row[key] for key in returned_keys if key in row and row[key] is not None}
        
        print(f"parameter(0): {row['parameter']}")
        # 1. add mandatory simple parameters by default
        if row["mandatory"] == 1 and not ("type" in row and row["type"] is not None and ("array" in row["type"].lower() or "object" in row["type"].lower())):
            return [returned_info]

        # have to let agent decide
        # 2. construct the message
        message_obj = {
            "user_requirement": self.user_requirement,
            "api_name": self.api_name,
            "parameter": row["parameter"],
            "description": row["description"],
        }
        if row["type"] is not None:
            message_obj["type"] = row["type"]
        if row["mandatory"] == 1:
            message_obj["mandatory"] = row["mandatory"]
        
        # 3. send the message and handle response
        selected_str = self.send_message_to_agent(recipient_agent_name="Param Selector", message=json.dumps(message_obj, ensure_ascii=False), parameter=message_obj["parameter"])
        
        if "不需要该参数" in selected_str:
            return []
        elif "需要该参数" in selected_str:
            return [returned_info]
        else:
            selected = try_parse_json(selected_str)
            assert_list_of_dicts(selected)
            return selected

    def run(self):
        debug_parallel = os.getenv("DEBUG_API_AGENTS_PARALLEL")

        # 1. get general information about this API
        apis_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='apis', condition=f'name=\'{self.api_name}\'')
        print(f"api_name: {self.api_name}")
        assert len(apis_df) == 1, f"API '{self.api_name}' does not exist or has duplicates."
        api_row = apis_df.iloc[0]
        api_id = api_row.loc["id"]
        root_table_id = api_row.loc["root_table_id"]

        # 2. call Param Selector to decide whether to select URI parameters
        uri_parameters_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='uri_parameters', condition=f'api_id=\'{api_id}\'')
        selected_uri_params = []

        if debug_parallel is not None and debug_parallel.lower() == "true":
            for _, row in uri_parameters_df.iterrows():
                selected_uri_params += self.select_uri_parameter(row)

        else:
            with ThreadPoolExecutor() as executor:
                futures = []
                for _, row in uri_parameters_df.iterrows():
                    futures.append(executor.submit(self.select_uri_parameter, row))
                for future in as_completed(futures):
                    selected_uri_params += future.result()

        # 3. Call SelectParamTable() to decide whether to select request parameters
        select_param_table_instance = SelectParamTable(caller_tool = self,
                                                       user_requirement = self.user_requirement,
                                                       api_name=self.api_name,
                                                       table_id=root_table_id)
        selected_request_params_str = select_param_table_instance.run()
        selected_request_params = try_parse_json(selected_request_params_str)
        assert_list_of_dicts(selected_request_params)

        # 4. assemble the information and return
        info = selected_uri_params + selected_request_params
        # selected_uri_params and selected_request_params are both like [{"parameter": "param1", "description": "description1"}, {"parameter": "param2", "description": "description2"}, ...]

        return json.dumps(info, ensure_ascii=False)
