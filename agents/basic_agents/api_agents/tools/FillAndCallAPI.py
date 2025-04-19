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
    param_list: list = Field(..., description="目标API所需参数列表，其中每一项都需要包括\"parameter\", \"id\", \"description\", \"label\", \"type\", \"value\"")
    api_name: str = Field(..., description="目标API名")

    def filling_param(self, name, id, api_id):
        param_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"id={id}")
        param_row = param_df.iloc[0]
        table_id = param_row.loc["table_id"]
        parent_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"api_id={api_id} AND ref_table_id={table_id}")
        if len(parent_df) == 0:
            return [{"name": name, "type": param_row.loc["type"]}]
        parent_row = parent_df.iloc[0]
        param_list = self.filling_param(name=parent_row.loc["parameter"], id=parent_row["id"], api_id=api_id)
        return [{"name": name, "type": param_row.loc["type"]}] + param_list
    
    def uri_replace_params(self, uri: str, uri_params: dict):
        uri = uri.split('?', 1)[0]
        tail_params = uri_params.copy()
        for parameter, value in uri_params.items():
            if ('{' + parameter + '}') in uri:
                uri = uri.replace('{' + parameter + '}', str(value))
                del tail_params[parameter]
        if tail_params:
            if "?" not in uri:
                uri = uri + "?"
            for parameter, value in tail_params.items():
                if uri.endswith("?"):
                    uri = uri + parameter + "=" + str(value)
                else:
                    uri = uri + "&" + parameter + "=" + str(value)
        return uri
    
    def merge_dict(self, dict1, dict2):
        merge_dict = dict1.copy()
        for key, value in dict2.items():
            if key in merge_dict:
                if isinstance(value, dict) and isinstance(merge_dict[key], dict):
                    merge_dict[key] = self.merge_dict(merge_dict[key], value)
                elif isinstance(value, list) and isinstance(merge_dict[key], list):
                    for param in value:
                        label = param["label"]
                        fl = False
                        for i, param1 in enumerate(merge_dict[key]):
                            if param1["label"] == label:
                                fl = True
                                merge_dict[key][i] = {
                                    "label": label,
                                    "value": self.merge_dict(param1["value"], param["value"])
                                }
                        if not fl:
                            merge_dict[key].append(param)
            else:
                merge_dict[key] = value
        return merge_dict
    
    def flatten_dict(self, request_params: dict) -> dict:
        result_dict = {}
        for key, value in request_params.items():
            if isinstance(value, list):
                new_list = []
                for param in value:
                    new_list.append(self.flatten_dict(param["value"]))
                result_dict[key] = new_list
            elif isinstance(value, dict):
                result_dict[key] = self.flatten_dict(value)
            else:
                result_dict[key] = value
        return result_dict

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
                labels = param["label"] if "label" in param else []
                value = {}
                for parameter in parent_param_list:
                    if parameter["name"] == param["parameter"]:
                        value = {parameter["name"]: param["value"]}
                    else:
                        if "array" in parameter["type"].lower():
                            value = {
                                parameter["name"]: [{
                                    "label": labels[0],
                                    "value": value
                                }]}
                            labels = labels[1: ] if len(labels) > 1 else []
                        else:
                            value = {parameter["name"]: value}
                request_param_values = self.merge_dict(request_param_values, value)

        request_param_values = self.flatten_dict(request_param_values)
        print(json.dumps(request_param_values, ensure_ascii=False, indent=4))
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