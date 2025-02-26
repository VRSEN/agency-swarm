from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api = [
            {
                "api name": "变更集群规格",
                "introduction": "变更一个指定集群的规格。"
            }
        ]
        return api
