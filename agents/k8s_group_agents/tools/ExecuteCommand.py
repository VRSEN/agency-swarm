from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os
import socket

HOST = "localhost"
PORT = 12345

IO_METHOD = os.getenv("DEBUG_EXECUTECOMMAND_METHOD") or "socket"

class ExecuteCommand(BaseTool):
    '''执行命令行命令'''
    command: str = Field(..., description="需要执行的命令")
    def run(self):
        # 把命令发给环境
        if IO_METHOD == "socket":
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.connect((HOST, PORT))
                    print(f"ExecuteCommand: Connected to k8s environment.")

                    print(f"ExecuteCommand: Sending command: '{self.command}'")
                    s.sendall(self.command.encode('utf-8'))

                    # 收到output
                    output = s.recv(1024).decode('utf-8')
                    print(f"ExecuteCommand: Received result: '{output}'")

                except ConnectionRefusedError:
                    print(f"ExecuteCommand: Could not connect to k8s environment at {HOST}:{PORT}. Is it running?")
                except Exception as e:
                    print(f"ExecuteCommand: An error occurred: {e}")
            print("ExecuteCommand: Connection closed.")

            check_result = self.send_message_to_agent(recipient_agent_name="check_log_agent", message=json.dumps({"command": self.command, "output": output}, indent=4, ensure_ascii=False))

            if "该任务执行失败" in check_result:
                return {"tool": "ExecuteCommand", "command": self.command, "result": "FAIL", "reason": check_result}
            return {"tool": "ExecuteCommand", "command": self.command, "result": "SUCCESS", "reason": check_result}
        else:
            print(f"ExecuteCommand: command = {self.command}")
            output = input("input result: ")
            check_result = self.send_message_to_agent(recipient_agent_name="check_log_agent", message=json.dumps({"command": self.command, "output": output}, indent=4, ensure_ascii=False))

            if "该任务执行失败" in check_result:
                return {"tool": "ExecuteCommand", "command": self.command, "result": "FAIL", "reason": check_result}
            return {"tool": "ExecuteCommand", "command": self.command, "result": "SUCCESS", "reason": check_result}
