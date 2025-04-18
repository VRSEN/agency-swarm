from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field
class GetParamValue(BaseTool):
    """根据用户需求和上下文信息获取参数值"""
    user_requirement: str = Field(
        ..., description="自然语言描述的用户需求"
    )
    param_list: list = Field(
        ..., description="需要获取值的参数列表，其中每一项都需要包括\"parameter\", \"id\", \"description\", \"type\", \"label\""
    )

    def run(self):
        message = {
            "user_requirement": self.user_requirement,
            "param_list": self.param_list
        }
        result = self.send_message_to_agent(recipient_agent_name="param_asker", message=json.dumps(message, ensure_ascii=False))
        return result
