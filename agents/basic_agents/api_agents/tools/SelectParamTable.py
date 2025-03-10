from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.utils import try_parse_json, assert_list_of_dicts

class SelectParamTable(BaseTool):
    '''
    根据用户需求，选择一个 API 在一张参数表中的所有需要填写的参数字段。
    '''

    user_requirement: str = Field(..., description="自然语言的用户需求")
    api_name: str = Field(..., description="目标API名")
    table_id: int = Field(default=0, description="表号，常见于“详情请参见表...”，默认值为0")

    def select_parameter(self, row):
        returned_keys = ["parameter", "description", "type"]
        returned_info = {key: row[key] for key in returned_keys if key in row and row[key] is not None}
        
        print(f"parameter: {row['parameter']}")
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
        
        # search upwards for all parents of this parameter, add their descriptions to message
        parent_ref_table_id = row["table_id"]
        while parent_ref_table_id is not None:
            parent_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"api_id={row['api_id']} AND ref_table_id={parent_ref_table_id}")
            if len(parent_df) == 0:
                break
            parent_row = parent_df.iloc[0]
            if "parents_description" not in message_obj:
                message_obj["parents_description"] = {}
            message_obj["parents_description"][parent_row["parameter"]] = parent_row["description"]
            parent_ref_table_id = parent_row["table_id"]
        # add parents' description to returned_info too
        if "parents_description" in message_obj:
            returned_info["parents_description"] = message_obj["parents_description"]

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

        # 1. get ID of this API
        apis_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='apis', condition=f'name=\'{self.api_name}\'')
        print(f"api_name: {self.api_name}")
        assert len(apis_df) == 1, f"API '{self.api_name}' does not exist or has duplicates."
        api_row = apis_df.iloc[0]
        api_id = api_row.loc["id"]

        # 2. for each parameter in this table, call Param Selector to decide whether to select it.
        param_table_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"api_id='{api_id}' AND table_id='{self.table_id}'")
        selected_params = []

        if debug_parallel is not None and debug_parallel.lower() == "true":
            for _, row in param_table_df.iterrows():
                selected_params += self.select_parameter(row)

        else:
            with ThreadPoolExecutor() as executor:
                futures = []
                for _, row in param_table_df.iterrows():
                    futures.append(executor.submit(self.select_parameter, row))
                for future in as_completed(futures):
                    selected_params += future.result()

        return json.dumps(selected_params, ensure_ascii=False)
