from agency_swarm.tools import BaseTool
import json
from pydantic import Field
import os

class ReadJsonFile(BaseTool):
    """Read a JSON File"""
    file_name: str = Field(
        ..., description="需要读取的json文件名称"
    )

    def run(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, self.file_name)
        print(file_path)
        with open(file_path, 'r') as file:
            json_data = json.load(file)
            json_txt = json.dumps(json_data)
            return json_txt
        