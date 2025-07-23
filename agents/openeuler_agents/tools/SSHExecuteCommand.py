from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os

HOST = "localhost"
PORT = 22
USERNAME = "aaa"
PASSWORD = "bbb"

class SSHExecuteCommand(BaseTool):
    '''通过SSH执行命令行命令'''
    command: str = Field(..., description="需要执行的命令")

    def run(self):
        print(self.command)
        return input("Result: ")
