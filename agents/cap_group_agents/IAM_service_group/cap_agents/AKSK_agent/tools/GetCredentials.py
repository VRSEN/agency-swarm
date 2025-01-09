from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class GetCredentials(BaseTool):
    """
    获取 access_key 和 secret_key 并以json格式返回
    """
    def run(self):
        try:
            import json
            json_file_name = 'credentials.json'
            current_dir = os.path.dirname(os.path.abspath(__file__))
            json_file_path = os.path.join(current_dir, json_file_name)
            print(f"current_dir: {current_dir}")
            with open(json_file_path, 'r') as f:
                credentials = json.load(f)
                
            access_key = credentials.get('access_key')
            secret_key = credentials.get('secret_key')
            
            if not access_key or not secret_key:
                raise ValueError("Missing required credentials in JSON file")
                
            return str(credentials)
            
        except FileNotFoundError:
            raise FileNotFoundError(f"Credentials file not found: {json_file_path}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format in file: {json_file_path}")
