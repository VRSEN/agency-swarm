
from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api_name": "查询弹性云服务器单个磁盘信息",
        "introduction": "用于查询弹性云服务器挂载的单个磁盘信息。"
    },
    {
        "api_name": "查询弹性云服务器挂载磁盘列表信息",
        "introduction": "用于查询弹性云服务器挂载的磁盘列表信息。"
    },
    {
        "api_name": "查询弹性云服务器挂载磁盘列表详情信息",
        "introduction": "用于查询弹性云服务器挂载的磁盘列表详情信息。"
    },
    {
        "api_name": "弹性云服务器挂载磁盘",
        "introduction": "把磁盘挂载到弹性云服务器上。"
    },
    {
        "api_name": "弹性云服务器卸载磁盘",
        "introduction": "从弹性云服务器中卸载磁盘。"
    },
    {
        "api_name": "修改弹性云服务器挂载的单个磁盘信息",
        "introduction": "修改云服务器挂载的单个磁盘信息。"
    }
]

        return api