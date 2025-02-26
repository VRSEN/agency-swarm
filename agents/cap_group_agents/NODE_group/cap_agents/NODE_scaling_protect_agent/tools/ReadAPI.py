from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api = [
    {
        "api name": "节点开启缩容保护",
        "introduction": "用于节点开启缩容保护，开启缩容保护的节点无法通过修改节点池个数的方式被缩容。"
    },
    {
        "api name": "节点关闭缩容保护",
        "introduction": "用于节点关闭缩容保护，关闭缩容保护的节点可以通过修改节点池个数的方式被缩容，只允许按需节点关闭缩容保护。"
    }
]
        return api
