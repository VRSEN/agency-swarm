from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime
import json
import os

class WriteFile(BaseTool):
    '''将文本写入文件'''
    file_name: str = Field(..., description="需要写入的txt文件名")
    content: str = Field(..., description="需要在该txt文件中写入的内容")

    def run(self):
        #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #file_name_ = f"text_{timestamp}.txt"
        print(self.file_name)
        print(self.content)
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        file_path = os.path.join(agents_dir, "files", self.file_name)
        # TODO: 将写文件发给环境
        try:
        # 实际写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.content)    
            output = "File written successfully"
        except Exception as e:
            output = f"File write failed: {str(e)}"
        

        check_result = self.send_message_to_agent(recipient_agent_name="check_log_agent", message=output)

        if "该任务执行失败" in check_result:
            return {"tool": "WriteFile", "result": "FAIL", "reason": check_result}
        return {"tool": "WriteFile",  "result": "SUCCESS", "reason": check_result}
