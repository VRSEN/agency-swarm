
from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api = [
            {
                "api_name": "查询规格详情和规格扩展信息列表",
                "introduction": "查询云服务器规格详情信息和规格扩展信息列表。"
            },
            {
                "api_name": "查询规格销售策略",
                "introduction": "查询竞价计费模式以及IES场景的规格销售策略列表。"
            },
            {
                "api_name": "查询云服务器规格变更支持列表",
                "introduction": "通过指定弹性云服务器规格，查询该规格可以变更的规格列表。"
            }
        ]

        return api