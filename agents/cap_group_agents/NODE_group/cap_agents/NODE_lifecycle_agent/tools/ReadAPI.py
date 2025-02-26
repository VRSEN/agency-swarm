from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api name": "创建节点",
        "introduction": "在指定集群下创建节点。"
    },
    {
        "api name": "获取指定的节点",
        "introduction": "通过节点ID获取指定节点的详细信息。"
    },
    {
        "api name": "获取集群下所有节点",
        "introduction": "通过集群ID获取指定集群下所有节点的详细信息。"
    },
    {
        "api name": "更新指定的节点",
        "introduction": "更新指定的节点。"
    },
    {
        "api name": "删除节点",
        "introduction": "删除指定的节点。"
    },
    {
        "api name": "纳管节点",
        "introduction": "在指定集群下纳管节点。"
    },
    {
        "api name": "重置节点",
        "introduction": "在指定集群下重置节点。"
    },
    {
        "api name": "同步节点",
        "introduction": "同步节点。"
    },
    {
        "api name": "批量同步节点",
        "introduction": "批量同步节点。"
    }
]

        return api
