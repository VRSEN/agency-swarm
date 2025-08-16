from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from agents.openeuler_agents.tools.ssh_executor import SSHCommandExecutor

HOST = "192.168.40.140"
PORT = 22
USERNAME = "root"
PASSWORD = "1723"

SSH_CONNECTION_ERROR = -1

executor = SSHCommandExecutor(HOST, USERNAME, PASSWORD, PORT)

class SSHExecuteCommand(BaseTool):
    '''通过SSH执行命令行命令'''
    command: str = Field(..., description="需要执行的命令")

    def run(self):
        print(f"SSHExecuteCommand: executing {self.command}")
        success_connect = executor.connect()
        if not success_connect:
            res = {
                'full_stdout': '',
                'full_stderr': '',
                'final_status': SSH_CONNECTION_ERROR,
            }
        else:
            res = executor.execute_command_common(command=self.command)

        print("SSH:", json.dumps({"command": self.command, "result": res}, indent=4, ensure_ascii=False))
        
        check_result = self.send_message_to_agent(recipient_agent_name="check_log_agent", message=json.dumps({"command": self.command, "result": res}, indent=4, ensure_ascii=False))

        if "该任务执行失败" in check_result:
            return {"result": "FAIL", "context": check_result}
        return {"result": "SUCCESS", "context": check_result}

# if __name__=="__main__":
#     tool = SSHExecuteCommand(command="for i in $(seq 1 3); do echo 'Line $i (yield)'; sleep 1; done")
#     print(tool.run())
