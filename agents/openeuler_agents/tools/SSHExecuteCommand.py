from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from agents.openeuler_agents.tools.ssh_executor import SSHCommandExecutor

HOST = "127.0.0.1"
PORT = 8022
USERNAME = "tommenx"
PASSWORD = "test"

SSH_CONNECTION_ERROR = -1

executor = SSHCommandExecutor(HOST, USERNAME, PASSWORD, PORT)

class SSHExecuteCommand(BaseTool):
    '''通过SSH执行命令行命令'''
    command: str = Field(..., description="需要执行的命令")

    def run(self):
        
        success_connect = executor.connect()
        if not success_connect:
            return json.dumps({
            'full_stdout':'',
            'full_stderr':'',
            'final_status':SSH_CONNECTION_ERROR,
        })
        res = executor.execute_command_common(command=self.command)
        return json.dumps(res)

if __name__=="__main__":
    tool = SSHExecuteCommand(command="for i in $(seq 1 3); do echo 'Line $i (yield)'; sleep 1; done")
    print(tool.run())

 