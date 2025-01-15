from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.utils import try_parse_json, assert_list_of_dicts

from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable

class SelectAPIParam(BaseTool):
    '''
    根据用户需求，选择一个 API 的所有需要填写的参数字段，包括必选参数、用户选择的可选参数和环境参数。
    '''

    api_name: str = Field(..., description="目标API名")
    user_requirement: str = Field(..., description="自然语言的用户需求")

    def run(self):

        # 1. get general information about this API
        api_info_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='api_info', condition=f'name=\'{self.api_name}\'')
        assert len(api_info_df) == 1, "api_name should have exactly 1 match"
        api_info = api_info_df.iloc[0]
        method = api_info.loc["method"]     # assume no parameters
        uri = api_info.loc["uri"]           # assume some parameters

        # 2. call Param Selector to decide whether to select URI parameters
        uri_parameters_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='uri_parameters', condition=f'api_name=\'{self.api_name}\'')
        selected_uri_params = []
        for _, row in uri_parameters_df.iterrows():
            returned_keys = ["parameter", "description", "type"]
            returned_info = {key: row[key] for key in returned_keys if key in row and row[key] is not None}

            # 2.1. add mandatory simple parameters by default
            if row["mandatory"] == 1 and not ("type" in row and row["type"] is not None and ("array" in row["type"].lower() or "object" in row["type"].lower())):
                selected_uri_params.append(returned_info)
                continue
            
            # have to let agent decide
            # 2.2. construct the message
            message_obj = {
                "user_requirement": self.user_requirement,
                "api_name": self.api_name,
                "parameter": row["parameter"],
                "description": row["description"]
            }
            if row["type"] is not None:
                message_obj["type"] = row["type"]
            if row["mandatory"] == 1:
                message_obj["mandatory"] = row["mandatory"]
            
            # 2.3. send the message and handle response
            selected_str = self.send_message_to_agent(recipient_agent_name="Param Selector", message=json.dumps(message_obj, ensure_ascii=False))

            if "不需要该参数" in selected_str:
                continue
            elif "需要该参数" in selected_str:
                selected_uri_params.append(returned_info)
            else:
                selected = try_parse_json(selected_str)
                assert_list_of_dicts(selected)
                selected_uri_params += selected

        # 3. Call SelectParamTable() to decide whether to select request parameters
        select_param_table_instance = SelectParamTable(caller_tool = self,
                                                       user_requirement = self.user_requirement,
                                                       api_name=self.api_name,
                                                       table_id=1) # assume root table is always table 1
        selected_request_params_str = select_param_table_instance.run()
        selected_request_params = try_parse_json(selected_request_params_str)
        assert_list_of_dicts(selected_request_params)

        # 4. assemble the information and return
        info = selected_uri_params + selected_request_params
        # selected_uri_params and selected_request_params are both like [{"parameter": "param1", "description": "description1"}, {"parameter": "param2", "description": "description2"}, ...]

        return json.dumps(info, ensure_ascii=False)
