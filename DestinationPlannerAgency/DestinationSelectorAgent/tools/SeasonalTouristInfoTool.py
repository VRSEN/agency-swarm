from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("TOURISTINFO_API_KEY")

class SeasonalTouristInfoTool(BaseTool):
    """
    Retrieves seasonal tourist information for a given destination using the TouristInfo API.
    """
    
    destination: str = Field(..., description="Destination for which seasonal tourist information is to be retrieved.")

    def run(self):
        base_url = "https://api.touristinfo.com/v1/seasonalInfo"
        params = {"destination": self.destination, "api_key": api_key}
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error fetching seasonal tourist information: {response.reason}"