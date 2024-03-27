from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("BUDGET_MANAGEMENT_API_KEY")

class BudgetManagementTool(BaseTool):
    """
    Provides budget and packing suggestions for a trip to the specified city, considering the given duration.
    """
    
    city: str = Field(..., description="City for budget and packing suggestions.")
    duration: int = Field(..., description="Duration of the trip in days.")

    def run(self):
        base_url = "https://api.budgetmanagement.com/v1/suggestions"
        params = {"city": self.city, "duration": self.duration, "api_key": api_key}
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error fetching budget and packing suggestions: {response.reason}"