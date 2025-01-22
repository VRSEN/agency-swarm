from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os

class ReadFile(BaseTool):

    read_file_path: str = Field(..., description="需要读取的文件的路径")

    def run(self):
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        target_path = os.path.join(agents_dir, "files", self.read_file_path)
        with open(target_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
        if len(file_content) > 20000:
            file_content = file_content[: 20000]
        return file_content
  