from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api_name": "创建云硬盘快照",
        "introduction": "创建云硬盘快照。"
    },
    {
        "api_name": "删除云硬盘快照",
        "introduction": "删除云硬盘快照。"
    },
    {
        "api_name": "更新云硬盘快照",
        "introduction": "更新云硬盘快照。"
    },
    {
        "api_name": "查询云硬盘快照详情列表",
        "introduction": "查询云硬盘快照详情列表。"
    },
    {
        "api_name": "查询单个云硬盘快照详情",
        "introduction": "查询单个云硬盘快照信息。"
    },
    {
        "api_name": "回滚快照到云硬盘",
        "introduction": "将快照数据回滚到云硬盘。"
    }
]

        return api