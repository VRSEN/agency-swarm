from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("TRIPADVISOR_API_KEY")

class TripAdvisorIntegrationTool(BaseTool):
    """
    Interacts with the TripAdvisor API to fetch information about activities, restaurants, and attractions based on user preferences.
    """

    location: str = Field(
        ..., description="Location of interest for fetching TripAdvisor data.")
    category: str = Field(
        ..., description="Category of interest such as 'restaurants', 'activities', or 'attractions'.")

    def run(self):
        base_url = 'https://api.tripadvisor.com/api/partner/2.0/location/12345/attractions'
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        params = {
            'location': self.location,
            'category': self.category,
            'limit': 20
        }
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return 'Failed to fetch TripAdvisor information.'
