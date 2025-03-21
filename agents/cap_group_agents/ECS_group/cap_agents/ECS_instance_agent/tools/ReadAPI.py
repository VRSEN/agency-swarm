from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api = [
            {
                "api_name": "创建云服务器",
                "introduction": "创建一台或多台云服务器。"
            },
            {
                "api_name": "创建云服务器（按需）",
                "introduction": "创建一台或多台按需付费方式的云服务器。"
            },
            {
                "api_name": "删除云服务器",
                "introduction": "根据指定的云服务器ID列表，删除云服务器。"
            },
            {
                "api_name": "查询云服务器详情",
                "introduction": "查询弹性云服务器的详细信息。"
            },
            {
                "api_name": "查询云服务器详情列表",
                "introduction": "根据用户请求条件筛选、查询所有的弹性云服务器，并关联获取弹性云服务器的详细信息。"
            },
            {
                "api_name": "查询云服务器列表",
                "introduction": "据用户请求条件筛选、查询所有的弹性云服务器，并关联获取弹性云服务器的详细信息。"
            },
            {
                "api_name": "修改云服务器",
                "introduction": "修改云服务器信息，目前支持修改云服务器名称和描述。"
            },
            {
                "api_name": "冷迁移云服务器",
                "introduction": "将部署在专属主机上的弹性云服务器迁移至其他专属主机。"
            },
            {
                "api_name": "批量启动云服务器",
                "introduction": "根据给定的云服务器ID列表，批量启动云服务器。"
            },
            {
                "api_name": "批量关闭云服务器",
                "introduction": "根据给定的云服务器ID列表，批量关闭云服务器。"
            },
            {
                "api_name": "批量重启云服务器",
                "introduction": "根据给定的云服务器ID列表，批量重启云服务器。"
            }
        ]
        return api
