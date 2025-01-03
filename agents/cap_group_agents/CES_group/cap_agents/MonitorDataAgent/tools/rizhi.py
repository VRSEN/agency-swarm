from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class rizhi(BaseTool):
    '''
        用于记录日志信息
    '''
    # 收集到的日志信息
    information: str = Field(
        ..., description="Daemon Agent接收到的日志和各种记录."
    )

    def run(self):
        information= self.information
        filename = 'rizhi.txt'
        # 获取当前脚本的目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 构建完整的文件路径
        file_path = os.path.join(current_dir, filename)
        with open(file_path, 'a', encoding='utf-8') as file:
            # 写入内容到文件
            file.write(information + '\n') # 添加换行符以确保日志信息分行写入
        return 

