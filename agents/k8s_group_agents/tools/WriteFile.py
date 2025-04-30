from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os

class WriteFile(BaseTool):
    '''将文本写入文件'''
    file_name: str = Field(..., description="文件名")
    content: str = Field(..., description="需要写入的内容")
    def run(self):
        print(self.file_name)
        print(self.content)
        
        # TODO: 将写文件发给环境
        # 收到output
        # output = input(f"input WriteFile({self.command}) result:")
        output = "File written successfully"

        check_result = self.send_message_to_agent(recipient_agent_name="check_log_agent", message=output)

        if "该任务执行失败" in check_result:
            return {"result": "FAIL", "context": check_result}
        return {"result": "SUCCESS", "context": check_result}
