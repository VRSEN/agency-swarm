from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("RESTAURANT_PLATFORM_API_KEY")

class DiningReservationsTool(BaseTool):
    """
    Makes dining reservations at recommended restaurants based on user preferences and ratings.
    """
    
    city: str = Field(..., description="City for making dining reservations.")
    preferences: str = Field(..., description="Dining preferences for restaurant selection.")

    def run(self):
        base_url = "https://api.restaurantplatform.com/v1/reservations"
        params = {"city": self.city, "preferences": self.preferences, "api_key": api_key}
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error making dining reservations: {response.reason}"