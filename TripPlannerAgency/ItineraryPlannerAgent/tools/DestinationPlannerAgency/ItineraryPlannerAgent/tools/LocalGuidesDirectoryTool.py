from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("LOCAL_GUIDES_API_KEY")

class LocalGuidesDirectoryTool(BaseTool):
    """
    Searches and retrieves available local guides from a directory based on the specified city and language.
    """
    
    city: str = Field(..., description="City where the guide service is needed.")
    language: str = Field(..., description="Preferred language for the guide service.")

    def run(self):
        base_url = "https://api.localguides.com/v1/search"
        params = {"city": self.city, "language": self.language, "api_key": api_key}
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error searching for local guides: {response.reason}"