from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE

from agents.basic_agents.api_agents.tools.GetCredentials import GetCredentials
from agents.basic_agents.api_agents.tools.RequestAPI import RequestAPI

class FillAndCallAPI(BaseTool):
    '''
    根据用户需求，填写并返回一个 API 的所有参数值。
    '''
    param_list: list = Field(..., description="目标API所需参数列表")
    api_name: str = Field(..., description="目标API名")

    def filling_param(self, name, id, api_id):
        param_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"id={id}")
        param_row = param_df.iloc[0]
        table_id = param_row.loc["table_id"]
        parent_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"api_id={api_id} AND ref_table_id={table_id}")
        if len(parent_df) == 0:
            return [name]
        parent_row = parent_df.iloc[0]
        param_list = self.filling_param(name=parent_row.loc["parameter"], id=parent_row["id"], api_id=api_id)
        return [name] + param_list
    
    def uri_replace_params(self, uri, uri_params):
        for parameter, value in uri_params.items():
            uri = uri.replace('{' + parameter + '}', str(value))
        return uri
    
    def merge_dict(self, dict1, dict2):
        merge_dict = dict1.copy()
        for key, value in dict2.items():
            if key in merge_dict:
                if isinstance(value, dict) and isinstance(merge_dict[key], dict):
                    merge_dict[key] = self.merge_dict(merge_dict[key], value)
            else:
                merge_dict[key] = value
        return merge_dict                   

    def run(self):
        # 1. get general information about this API
        apis_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='apis', condition=f'name=\'{self.api_name}\'')
        print(f"Filling api_name: {self.api_name}")
        assert len(apis_df) == 1, f"API '{self.api_name}' does not exist or has duplicates."
        api_row = apis_df.iloc[0]
        method = api_row.loc["method"]
        uri = api_row.loc["uri"]
        api_id = api_row.loc["id"]

        # 2. for each URI parameter, call Param Filler to decide its value
        uri_parameters_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='uri_parameters', condition=f'api_id=\'{api_id}\'')
        uri_param_values = {}

        name2parameter = {}
        for param in self.param_list:
            name2parameter[param["parameter"]] = param
        
        for _, row in uri_parameters_df.iterrows():
            key = row["parameter"]
            value = name2parameter[key]["value"]
            if value is not None:
                uri_param_values[key] = value

        request_param_values = {}
        for param in self.param_list:
            if uri_param_values.get(param["parameter"]) == None:
                parent_param_list = self.filling_param(name=param["parameter"], id=param["id"], api_id=api_id)
                value = {}
                for parameter in parent_param_list:
                    if parameter == param["parameter"]:
                        value = {parameter: param["value"]}
                    else:
                        value = {parameter: value}
                request_param_values = self.merge_dict(request_param_values, value)
                
        # 4. assemble the information and return
        # info = {
        #     "method": method,
        #     "uri": uri,
        #     "uri_parameters": uri_param_values,
        #     "request_body": request_param_values
        # }
        url = self.uri_replace_params(uri=uri, uri_params=uri_param_values)

        GetCredentialstool = GetCredentials(caller_tool=self)
        credentials = GetCredentialstool.run()

        RequestAPItool = RequestAPI(caller_tool=self, method=method, url=url, header="", body=json.dumps(request_param_values), access_key=credentials["access_key"], secret_key=credentials["secret_key"])
        file_path = RequestAPItool.run()

        return file_path
    
