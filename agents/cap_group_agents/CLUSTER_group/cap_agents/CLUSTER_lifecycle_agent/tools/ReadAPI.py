from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api = [
    {
        "api_name": "创建集群",
        "introduction": "创建一个空集群（即只有控制节点Master，没有工作节点Node）。"
    },
    {
        "api_name": "删除集群",
        "introduction": "删除一个指定的集群。"
    },
    {
        "api_name": "更新指定的集群",
        "introduction": "更新指定的集群。"
    },
    {
        "api_name": "获取指定的集群",
        "introduction": "获取指定集群的详细信息。"
    },
    {
        "api_name": "集群休眠",
        "introduction": "休眠一个指定的集群。"
    },
    {
        "api_name": "集群唤醒",
        "introduction": "唤醒一个指定的已休眠集群。"
    },
    {
        "api_name": "查询指定集群支持配置的参数列表",
        "introduction": "查询CCE服务下指定集群支持配置的参数列表。"
    },
    {
        "api_name": "批量添加指定集群的资源标签",
        "introduction": "批量添加指定集群的资源标签。"
    },
    {
        "api_name": "批量删除指定集群的资源标签",
        "introduction": "批量删除指定集群的资源标签。"
    }
]

        return api
