from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime
import os
import json
import yaml

class YAML_create(BaseTool):

    k8sYAML: dict = Field(..., description="k8s yaml配置信息")

    def run(self):
        info = self.k8sYAML
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..","..", ".."))
        target_path = os.path.join(agents_dir, "files", "configs")
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        yaml_file_name = f"deployment_{current_time}.yaml"
        yaml_file_path = os.path.join(target_path, yaml_file_name)
        with open(yaml_file_path, "w", encoding="utf-8") as file:
            yaml.dump(info, file, sort_keys=False)
        return yaml_file_name
     