
from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api = [
    {
        "api name": "批量添加云服务器网卡",
        "introduction": "给云服务器添加一张或多张网卡。"
    },
    {
        "api name": "批量删除云服务器网卡",
        "introduction": "卸载并删除云服务器中的一张或多张网卡。"
    },
    {
        "api name": "查询云服务器网卡信息",
        "introduction": "用于查询云服务器网卡信息。"
    },
    {
        "api name": "云服务器切换虚拟私有云",
        "introduction": "用于云服务器切换虚拟私有云。"
    },
    {
        "api name": "更新云服务器指定网卡属性",
        "introduction": "更新云服务器指定网卡属性，当前仅支持更新网卡IP。"
    }
]
        return api