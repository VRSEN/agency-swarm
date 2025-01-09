from agency_swarm.tools import BaseTool
import json
from pydantic import Field

class ReadJsonFile(BaseTool):
    """Read a JSON File"""
    file_name: str = Field(
        ..., description="需要读取的json文件名称"
    )

    def run(self):
        file_path = "/root/agency-swarm-cover/agents/files/" + self.file_name
        print(file_path)
        with open(file_path, 'r') as file:
            json_data = json.load(file)
            json_txt = json.dumps(json_data)
            return json_txt
        