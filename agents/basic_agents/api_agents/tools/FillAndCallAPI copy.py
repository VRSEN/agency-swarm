from pydantic import Field
import json

import sys
sys.path.append("D:\\MA\\agency-swarm-cover")

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE

from agents.basic_agents.api_agents.tools.GetCredentials import GetCredentials
from agents.basic_agents.api_agents.tools.RequestAPI import RequestAPI

class FillAndCallAPI():
    '''
    根据用户需求，填写并返回一个 API 的所有参数值。
    '''
    param_list = [{'parameter': 'project_id', 'id': 237, 'description': '**参数解释：**\n项目ID，获取方式请参见如何获取接口URI中参数。\n**约束限制：**\n不涉及\n**取值范围：**\n账号的项目ID\n**默认取值：**\n不涉及', 'type': 'String', 'mandatory': 1, 'value': '1fc79a55369c436c833ddf4e124af1d8'}, {'parameter': 'endpoint', 'id': 236, 'description': '指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。\n例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。', 'type': 'String', 'mandatory': 1, 'value': 'cce.cn-north-4.myhuaweicloud.com'}, {'parameter': 'cluster_id', 'id': 238, 'description': '**参数解释：**\n集群ID，获取方式请参见如何获取接口URI中参数。\n**约束限制：**\n不涉及\n**取值范围：**\n集群ID\n**默认取值：**\n不涉及', 'type': 'String', 'value': 'eeb8f029-1c4b-11f0-a423-0255ac100260'}, {'parameter': 'nodepoolScaleUp', 'id': 239, 'description': '标明是否为nodepool下发的请求。若不为“NodepoolScaleUp”将自动更新对应节点池的实例数', 'type': 'String', 'value': 'None'}, {'parameter': 'apiVersion', 'id': 480, 'description': 'API版本，固定值“v3”，该值不可修改。', 'type': 'String', 'value': 'v3'}, {'parameter': 'kind', 'id': 479, 'description': 'API类型，固定值“Node”，该值不可修改。', 'type': 'String', 'value': 'Node'}, {'parameter': 'az', 'id': 492, 'description': '**参数解释** ：\n待创建节点所在的可用区，需要指定可用区（AZ）的名称，通过api创建节点不支持随机可用区。\nCCE支持的可用区请参考地区和终端节点。\n**约束限制** ：\n创建节点池并设置伸缩组时，该参数不允许填写为random。\n**取值范围** ：\n不涉及\n**默认取值** ：\n不涉及', 'type': 'String', 'value': 'cn-north-4a'}, {'parameter': 'flavor', 'id': 491, 'description': '**参数解释** ：\n节点的规格，CCE支持的节点规格请参考节点规格说明获取。\n**约束限制** ：\n不涉及\n**取值范围** ：\n不涉及\n**默认取值** ：\n不涉及', 'type': 'String', 'value': 'c6.large.2'}, {'parameter': 'volumetype', 'id': 500, 'description': '**参数解释** ：\n磁盘类型，取值请参见创建云服务器 中“root_volume字段数据结构说明”。\n**约束限制** ：\n不涉及\n**取值范围** ：\n- SAS：高IO，是指由SAS存储提供资源的磁盘类型。\n- SSD：超高IO，是指由SSD存储提供资源的磁盘类型。\n- SATA：普通IO，是指由SATA存储提供资源的磁盘类型。EVS已下线SATA磁盘，仅存量节点有此类型的磁盘。\n- ESSD：极速型SSD云硬盘，是指由极速型SSD存储提供资源的磁盘类型。\n- GPSSD：通用型SSD云硬盘，是指由通用型SSD存储提供资源的磁盘类型。\n- ESSD2：极速型SSD V2云硬盘，是指由极速型SSD V2存储提供资源的磁盘类型。\n- GPSSD2：通用型SSD V2云硬盘，是指由通用型SSD V2存储提供资源的磁盘类型。\n说明：\n了解不同磁盘类型的详细信息，链接请参见磁盘类型及性能介绍。\n**默认取值** ：\n不涉及', 'type': 'String', 'value': 'SSD'}, {'parameter': 'size', 'id': 499, 'description': '**参数解释** ：\n磁盘大小，单位为GiB。\n**约束限制** ：\n不涉及\n**取值范围** ：\n- 系统盘取值范围：40~1024\n- 第一块数据盘取值范围：20~32768(当缺省磁盘初始化配置管理参数storage时，数据盘取值范围：100-32768)\n- 其他数据盘取值范围：10~32768(当缺省磁盘初始化配置管理参数storage时，数据盘取值范围：100-32768)\n**默认取值** ：\n不涉及', 'type': 'Integer', 'label': ['6e12d5ab03deffa0b215c9d526820eb8'], 'value': 50}, {'parameter': 'volumetype', 'id': 515, 'description': '**参数解释** ：\n磁盘类型，取值请参见创建云服务器 中“root_volume字段数据结构说明”。\n**约束限制** ：\n不涉及\n**取值范围** ：\n- SAS：高IO，是指由SAS存储提供资源的磁盘类型。\n- SSD：超高IO，是指由SSD存储提供资源的磁盘类型。\n- SATA：普通IO，是指由SATA存储提供资源的磁盘类型。EVS已下线SATA磁盘，仅存量节点有此类型的磁盘。\n- ESSD：极速型SSD云硬盘，是指由极速型SSD存储提供资源的磁盘类型。\n- GPSSD： 通用型SSD云硬盘，是指由通用型SSD存储提供资源的磁盘类型。\n- ESSD2：极速型SSD V2云硬盘，是指由极速型SSD V2存储提供资源的磁盘类型。\n- GPSSD2：通用型SSD V2云硬盘，是指由通用型SSD V2存储提供资源的磁盘类型。\n说明：\n了解不同磁盘类型的详细信息，链接请参见磁盘类型及性能介绍。\n**默认取值** ：\n不涉及', 'type': 'String', 'value': 'SSD'}, {'parameter': 'size', 'id': 514, 'description': '**参数解释** ：\n磁盘大小，单位为GiB。\n**约束限制** ：\n不涉及\n**取值范围** ：\n- 系统盘取值范围：40~1024\n- 第一块数据盘取值范围：20~32768(当缺省磁盘初始化配置管理参数storage时，数据盘取值范围：100-32768)\n- 其他数据盘取值范围：10~32768(当缺省磁盘初始化配置管理参数storage时，数据盘取值范围：100-32768)\n**默认取值** ：\n不涉及', 'type': 'Integer', 'label': ['6e12d5ab03deffa0b215c9d526820eb8'], 'value': 100}, {'parameter': 'password', 'id': 496, 'description': '**参数解释** ：\n登录密码，若创建节点通过用户名密码方式，即使用该字段，则响应体中该字段作屏蔽展示。\n**约束限制** ：\n创建节点时password字段需要加盐加密，具体方法请参见创建节点时password字段加盐加密。\n**取值范围** ：\n密码复杂度要求：\n- 长度为8-26位。\n- 密码至少必须包含大写字母、小写字母、数字和特殊字符（!@$%^-_=+[{}]:,./?）中的三种。\n- 密码不能包含用户名或用户名的逆序。\n**默认取值** ：\n不涉及', 'type': 'String', 'value': 'JDYkc2FsdCR1SzEzUEgvMy9rOHZRQ0UzRFBEVzFiZm1UMmVZSnFEQjMydzFxOVY5WUt3M2ZmR0JTZWN1N2ZNZlkzYmY5Z2ZDNlJlTHp6NGl3anc3WHM5RDFUcmNuLg=='}]
    api_name = "创建节点"

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
                    uri = uri + parameter + "=" + value
                else:
                    uri = uri + "&" + parameter + "=" + value
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
    
print("start")
F = FillAndCallAPI()
F.run()