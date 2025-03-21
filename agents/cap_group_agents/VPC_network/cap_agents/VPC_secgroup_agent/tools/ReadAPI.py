from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api_name": "创建安全组",
        "introduction": "用于创建安全组。"
    },
    {
        "api_name": "查询安全组",
        "introduction": "用于查询单个安全组。"
    },
    {
        "api_name": "查询安全组列表",
        "introduction": "用于查询安全组列表。"
    },
    {
        "api_name": "删除安全组",
        "introduction": "用于删除安全组。"
    },
    {
        "api_name": "创建安全组规则",
        "introduction": "用于创建安全组规则。"
    },
    {
        "api_name": "查询安全组规则",
        "introduction": "用于查询单个安全组规则。"
    },
    {
        "api_name": "查询安全组规则列表",
        "introduction": "用于查询安全组规则列表。"
    },
    {
        "api_name": "删除安全组规则",
        "introduction": "用于删除安全组规则。"
    }
]

        return api