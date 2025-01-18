from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class GetCredentials(BaseTool):
    """
    获取 access_key 和 secret_key 并以json格式返回
    """
    def run(self):
        access_key = os.getenv("HUAWEICLOUD_ACCESS_KEY")
        if not access_key:
            raise ValueError("HUAWEICLOUD_ACCESS_KEY is not set.")
        
        secret_key = os.getenv("HUAWEICLOUD_SECRET_KEY")
        if not secret_key:
            raise ValueError("HUAWEICLOUD_SECRET_KEY is not set.")
        
        credentials = {
            "access_key": access_key,
            "secret_key": secret_key,
        }
        return str(credentials)
