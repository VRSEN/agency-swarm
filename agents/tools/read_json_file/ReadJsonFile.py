from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field

class ReadJsonFile(BaseTool):
    """Read a JSON File"""
    file_name: str = Field(
        ..., description="需要读取的json文件名称"
    )

    def run(self):
        current_dir = "agents/files/"
        file_path = current_dir + self.file_name
        print(file_path)
        with open(file_path, 'r') as file:
            json_data = json.load(file)
            json_txt = json.dumps(json_data)
            return json_txt
        