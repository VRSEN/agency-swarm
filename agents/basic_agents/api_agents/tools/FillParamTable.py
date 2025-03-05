from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.utils import try_parse_json

class FillParamTable(BaseTool):
    '''
    根据用户需求，填写一个 API 在一张参数表中的所有参数值。
    '''

    user_requirement: str = Field(..., description="用户需求")
    api_name: str = Field(..., description="目标API名")
    table_id: int = Field(default=0, description="表号，常见于“详情请参见表...”，默认值为0")

    def fill_parameter(self, row):
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

        # 2. send the message and handle response
        value_str = self.send_message_to_agent(recipient_agent_name="Param Filler", message=json.dumps(message_obj, ensure_ascii=False))

        if "不需要该参数" in value_str:
            return None, None
        else:
            return row["parameter"], try_parse_json(value_str)

    def run(self):
        debug_parallel = os.getenv("DEBUG_API_AGENTS_PARALLEL")

        # 1. get ID of this API
        apis_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='apis', condition=f'name=\'{self.api_name}\'')
        assert len(apis_df) == 1, f"API '{self.api_name}' does not exist or has duplicates."
        api_row = apis_df.iloc[0]
        api_id = api_row.loc["id"]

        # 2. for each parameter in this table, call Param Filler to decide its value.
        param_table_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"api_id='{api_id}' AND table_id='{self.table_id}'")
        param_values = {}
        
        if debug_parallel is not None and debug_parallel.lower() == "true":
            for _, row in param_table_df.iterrows():
                key, value = self.fill_parameter(row)
                if value is not None:
                    param_values[key] = value

        else:
            with ThreadPoolExecutor() as executor:
                futures = []
                for _, row in param_table_df.iterrows():
                    futures.append(executor.submit(self.fill_parameter, row))
                for future in as_completed(futures):
                    key, value = future.result()
                    if value is not None:
                        param_values[key] = value

        return json.dumps(param_values, ensure_ascii=False)
