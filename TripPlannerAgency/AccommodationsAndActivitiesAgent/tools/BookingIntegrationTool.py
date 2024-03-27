from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("BOOKING_API_KEY")

class BookingIntegrationTool(BaseTool):
    """
    Interfaces with the Booking.com API to fetch accommodation options based on user preferences.
    """

    location: str = Field(
        ..., description="The desired location for accommodation.")
    budget: float = Field(
        ..., description="Maximum budget for accommodation.")
    dates: str = Field(
        ..., description="Travel dates in the format 'YYYY-MM-DD,YYYY-MM-DD'.")

    def run(self):
        base_url = 'https://distribution-xml.booking.com/2.0/json/hotelAvailability'
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        params = {
            'location': self.location,
            'price_range': f'0-{self.budget}',
            'checkin': self.dates.split(',')[0],
            'checkout': self.dates.split(',')[1]
        }
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return 'Failed to fetch accommodation options from Booking.com.'
