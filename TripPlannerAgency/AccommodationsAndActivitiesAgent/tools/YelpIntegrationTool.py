from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("YELP_API_KEY")

class YelpIntegrationTool(BaseTool):
    """
    Utilizes the Yelp Fusion API to fetch information about businesses, including activities and restaurants, based on user preferences.
    """

    location: str = Field(
        ..., description="Location of interest for activities and restaurants.")
    category: str = Field(
        ..., description="Category of interest such as 'restaurants' or 'activities'.")
    budget: int = Field(
        ..., description="Budget level from 1 to 4, with 1 being the least expensive.")

    def run(self):
        base_url = 'https://api.yelp.com/v3/businesses/search'
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        params = {
            'location': self.location,
            'categories': self.category,
            'price': self.budget,
            'limit': 20
        }
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return 'Failed to fetch business information from Yelp.'
