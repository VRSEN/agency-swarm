from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api_name": "重装弹性云服务器操作系统（安装 Cloud-init）",
        "introduction": "重装弹性云服务器的操作系统。支持弹性云服务器数据盘不变的情况下，使用原镜像重装系统盘。"
    },
    {
        "api_name": "切换弹性云服务器操作系统（安装 Cloud-init）",
        "introduction": "切换弹性云服务器操作系统。支持弹性云服务器数据盘不变的情况下，使用新镜像重装系统盘。"
    },
    {
        "api_name": "重装弹性云服务器操作系统（未安装 Cloud-init）",
        "introduction": "重装弹性云服务器的操作系统。"
    },
    {
        "api_name": "切换弹性云服务器操作系统（未安装 Cloud-init）",
        "introduction": "切换弹性云服务器操作系统。"
    }
]


        return api