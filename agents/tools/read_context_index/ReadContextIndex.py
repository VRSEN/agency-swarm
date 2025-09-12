from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field

class ReadContextIndex(BaseTool):
    """Read context_tree.json"""

    def run(self):
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        index_path = os.path.join(agents_dir, "files", "context_tree.json")
        print(f"ReadContextIndex: reading context_tree.json")
        try:
            with open(index_path, 'r') as f:
                existing_data = json.load(f)
        except:
            existing_data = []
        return json.dumps(existing_data, ensure_ascii=False)
