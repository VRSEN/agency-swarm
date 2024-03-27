from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("NUMBEO_API_KEY")

class CostOfLivingTool(BaseTool):
    """
    Retrieves the cost-of-living data for a specified location using the Numbeo API.
    """
    
    location: str = Field(..., description="Location for which cost-of-living data is to be retrieved.")

    def run(self):
        base_url = "https://www.numbeo.com/api/city_prices"
        params = {"query": self.location, "api_key": api_key}
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error fetching cost-of-living data: {response.reason}"