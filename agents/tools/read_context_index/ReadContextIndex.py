from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field

class ReadContextIndex(BaseTool):
    """Read context index"""

    def run(self):
        current_dir = os.path.join("agents", "files")
        index_path = os.path.join(current_dir, "context_index.json")
        print(index_path)
        try:
            with open(index_path, 'r') as f:
                existing_data = json.load(f)
        except:
            existing_data = []
        return existing_data
