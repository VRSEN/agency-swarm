from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api = [
    {
        "api_name": "创建节点池",
        "introduction": "在指定集群下创建节点池。"
    },
    {
        "api_name": "获取指定的节点池",
        "introduction": "通过节点池ID获取指定节点池的详细信息。"
    },
    {
        "api_name": "获取集群下所有节点池",
        "introduction": "通过集群ID获取指定集群下所有节点池的详细信息。"
    },
    {
        "api_name": "更新指定节点池",
        "introduction": "更新指定的节点池。"
    },
    {
        "api_name": "删除节点池",
        "introduction": "删除指定的节点池。"
    },
    {
        "api_name": "查询指定节点池支持配置的参数列表",
        "introduction": "查询CCE服务下指定节点池支持配置的参数列表。"
    },
    {
        "api_name": "查询指定节点池支持配置的参数内容",
        "introduction": "查询指定节点池支持配置的参数内容。"
    },
    {
        "api_name": "修改指定节点池配置参数的值",
        "introduction": "用于修改CCE服务下指定节点池配置参数的值。"
    },
    {
        "api_name": "伸缩节点池",
        "introduction": "伸缩指定的节点池。"
    },
    {
        "api_name": "同步节点池",
        "introduction": "同步节点池中已有节点的配置。"
    }
]
        return api
