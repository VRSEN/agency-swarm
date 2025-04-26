from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os

class ExecuteCommand(BaseTool):
    '''执行命令行命令'''
    command: str = Field(..., description="需要执行的命令")
    def run(self):
        print(self.command)
        
        # TODO: 把命令发给环境
        # 收到output
        output = ""

        check_result = self.send_message_to_agent(recipient_agent_name="check_log_agent", message=output)

        if "该任务执行失败" in check_result:
            return {"result": "FAIL", "context": check_result}
        return {"result": "SUCCESS", "context": check_result}
  