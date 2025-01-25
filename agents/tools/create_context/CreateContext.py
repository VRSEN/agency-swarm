from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field
import datetime

class CreateContext(BaseTool):
    """create a context (desicion or choose)"""
    context: str = Field(
        ..., description="需要写入context信息，可能是自然语言描述的决定或选择"
    )

    def run(self):
        result_json = {
            "content": self.context
        }
        now = datetime.datetime.now()
        formatted_time = now.strftime("%Y%m%d_%H%M%S")
        prefix = "context_"
        suffix = ".json"
        filename = f"{prefix}{formatted_time}{suffix}"
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        file_path = os.path.join(agents_dir, "files", "api_results", filename)
        with open(file_path, "w", encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False)
        return os.path.join("api_results", filename)
