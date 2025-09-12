from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class GetEndPointAndProjectID(BaseTool):
    def run(self):
        project_id = os.getenv("PROJECT_ID")
        return {
            "endpoint": "vpc.cn-north-4.myhuaweicloud.com",
            "poject_id": project_id
        }