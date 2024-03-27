from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("TOURISM_DATABASE_API_KEY")

class TourismSpotsSelectorTool(BaseTool):
    """
    Retrieves a list of recommended tourist spots from a tourism database for a given city.
    """
    
    city: str = Field(..., description="City for which tourist spots are to be retrieved.")
    interests: str = Field(..., description="User interests to filter spots.")

    def run(self):
        base_url = "https://api.tourismdb.com/v1/spots"
        params = {"city": self.city, "interests": self.interests, "api_key": api_key}
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error fetching tourist spots: {response.reason}"