from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api name": "创建云硬盘",
        "introduction": "创建一台或多台云硬盘。"
    },
    {
        "api name": "更新云硬盘",
        "introduction": "更新一个云硬盘的名称和描述。"
    },
    {
        "api name": "查询所有云硬盘详情",
        "introduction": "查询所有云硬盘的详细信息。"
    },
    {
        "api name": "查询单个云硬盘详情",
        "introduction": "查询单个云硬盘的详细信息。"
    },
    {
        "api name": "扩容云硬盘",
        "introduction": "对按需或者包周期云硬盘进行扩容。"
    },
    {
        "api name": "删除云硬盘",
        "introduction": "删除一个云硬盘，适用于按需云硬盘。"
    }
]

        return api