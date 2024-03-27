from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("OPENWEATHERMAP_API_KEY")

class WeatherForecastTool(BaseTool):
    """
    Provides weather forecast data for a specified location using the OpenWeatherMap API.
    """
    
    location: str = Field(..., description="Location for which weather forecast is to be retrieved.")

    def run(self):
        base_url = "http://api.openweathermap.org/data/2.5/forecast"
        params = {"q": self.location, "appid": api_key, "units": "metric"}
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return f"Error fetching weather data: {response.reason}"