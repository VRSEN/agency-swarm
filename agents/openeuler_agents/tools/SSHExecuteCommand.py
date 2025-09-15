from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from agents.openeuler_agents.tools.ssh_executor import SSHCommandExecutor

# HOST = "127.0.0.1"
HOST = "121.36.210.47"
PORT = 22
USERNAME = "root"
# PASSWORD = "mimacuowu,1"
PASSWORD = "Test123456!"

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
            return {"tool":"SSHExecuteCommand","command":self.command,"result": "FAIL", "reason":check_result}

        return  {"tool":"SSHExecuteCommand","command":self.command,"result": "SUCCESS", "reason":check_result}

if __name__=="__main__":
    tool = SSHExecuteCommand(command="for i in $(seq 1 3); do echo 'Line $i (yield)'; sleep 1; done")
    print(tool.run())
