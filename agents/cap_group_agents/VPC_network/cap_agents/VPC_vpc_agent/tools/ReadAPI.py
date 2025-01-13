from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api name": "创建VPC",
        "introduction": "创建虚拟私有云。"
    },
    {
        "api name": "查询VPC",
        "introduction": "查询虚拟私有云。"
    },
    {
        "api name": "查询VPC列表",
        "introduction": "查询虚拟私有云列表。"
    },
    {
        "api name": "更新VPC",
        "introduction": "更新虚拟私有云。"
    },
    {
        "api name": "删除VPC",
        "introduction": "删除虚拟私有云。"
    }
]

        return api