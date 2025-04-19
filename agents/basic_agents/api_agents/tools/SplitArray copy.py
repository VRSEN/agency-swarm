import os
import json
import re
import hashlib

import sys
sys.path.append("D:\\MA\\agency-swarm-cover")

from agency_swarm.tools import BaseTool

from agents.basic_agents.api_agents.tools.api_database import search_from_sqlite, API_DATABASE_FILE
from agents.basic_agents.api_agents.tools.SelectParamTable import SelectParamTable


class SplitArray(BaseTool):
    '''
    分割Array，再返回合并结果
    '''

    user_requirement = "在cn-north-4a可用区名为ccetest的CCE集群中创建一个节点。节点名称为node-1，集群ID为eeb8f029-1c4b-11f0-a423-0255ac100260。节点规格为c6.large.2，系统盘大小为50GB，数据盘大小为100GB，磁盘类型均为SSD。"
    api_name = "创建节点"
    parameter = "dataVolumes"
    id = 528
    description = "参数解释 ：\n节点的数据盘参数。针对专属云节点，参数解释与rootVolume一致。\n约束限制 ：\n- 磁盘挂载上限为虚拟机不超过16块，裸金属不超过10块。在此基础上还受限于虚拟机/裸金属规格可挂载磁盘数上限。（目前支持通过控制台和API为CCE节点添加多块数据盘）。\n- 如果数据盘正供容器运行时和Kubelet组件使用，则不可被卸载，否则将导致节点不可用。\n- 仅在选择系统盘作为系统组件存储磁盘时，允许为空。\n\n详情请参见表102"

    def extract_and_validate_json(self, text):
        try:
            data = json.loads(text)
            if isinstance(data, list) or isinstance(data, dict) or isinstance(data, str):
                return data
            else:
                return None
        except json.JSONDecodeError:
            pattern = r"```(?:json\s*)?(.*?)```"
            try:
                match = re.search(pattern, text, flags=re.DOTALL)
                if match:
                    data = json.loads(match.group(1).strip())
                    return data
                else:
                    return None
            except (ValueError, json.JSONDecodeError):
                return None
        

    def run(self):
        message_obj = {
            "user_requirement": self.user_requirement,
            "parameter": self.parameter,
            "description": self.description
        }
        result_json = [self.user_requirement]
        print(f"list: {result_json}")
        param_df = search_from_sqlite(database_path=API_DATABASE_FILE, table_name='request_parameters', condition=f"id={self.id}")
        param_row = param_df.iloc[0]
        ref_table_id = param_row.loc["ref_table_id"]
        result_list = []
        for user_req in result_json:
            SelectParamTabletool = SelectParamTable(caller_tool=self, user_requirement=user_req, api_name=self.api_name, table_id=ref_table_id)
            one_result = SelectParamTabletool.run()
            new_result_json = []
            for param in one_result:
                param["label"] = (param["label"] if "label" in param else []) + [hashlib.md5(user_req.encode()).hexdigest()]
                new_result_json.append(param)
            result_list += new_result_json
        return result_list
    
A = SplitArray()
print(A.run())