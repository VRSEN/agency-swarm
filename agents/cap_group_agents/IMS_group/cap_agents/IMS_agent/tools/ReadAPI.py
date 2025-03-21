from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ReadAPI(BaseTool):


    def run(self):
        api =[
    {
        "api_name": "查询镜像列表",
        "introduction": "根据不同条件查询镜像列表信息。"
    },
    {
        "api_name": "更新镜像信息",
        "introduction": "更新镜像信息接口，主要用于镜像属性的修改。"
    },
    {
        "api_name": "制作镜像",
        "introduction": "用于制作私有镜像。"
    },
    {
        "api_name": "镜像文件快速导入",
        "introduction": "使用上传至OBS桶中的超大外部镜像文件制作私有镜像。"
    },
    {
        "api_name": "使用外部镜像文件制作数据镜像",
        "introduction": "使用上传至OBS桶中的外部数据盘镜像文件制作数据镜像。"
    },
    {
        "api_name": "制作整机镜像",
        "introduction": "使用云服务器、云服务器备份或者云备份制作整机镜像。"
    },
    {
        "api_name": "注册镜像",
        "introduction": "用于将镜像文件注册为云平台未初始化的私有镜像。"
    },
    {
        "api_name": "导出镜像",
        "introduction": "用于用户将自己的私有镜像导出到指定的OBS桶中。"
    },
    {
        "api_name": "查询镜像支持的OS列表",
        "introduction": "查询当前区域弹性云服务器的OS兼容性列表。"
    }
]
        return api