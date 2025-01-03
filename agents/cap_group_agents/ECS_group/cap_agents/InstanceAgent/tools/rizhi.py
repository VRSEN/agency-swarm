from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class rizhi(BaseTool):
    '''
        用于记录日志信息
    '''
    # 收集到的日志信息
    information: str = Field(
        ..., description="Instance Agent需要记录的内容."
    )

    def run(self):
        information= self.information
        filename = 'rizhi.txt'
        # 获取当前脚本的目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 构建完整的文件路径
        file_path = os.path.join(current_dir, filename)
        # 打开文件，如果文件不存在则创建，'w'模式表示写入模式
        with open(file_path, 'w', encoding='utf-8') as file:
            # 写入内容到文件
            file.write(information)
        return 

