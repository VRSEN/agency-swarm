from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os

class ReadFile(BaseTool):

    response_info: json = Field(
        ..., description="API Filler发来的信息"
    )

    def run(self):
        result_dict = json.loads(response_info)
        file_path = result_dict.get("result_file_path")
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
        target_path = os.path.join(agents_dir, "files", file_path)
        with open(target_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
        
        return file_content
