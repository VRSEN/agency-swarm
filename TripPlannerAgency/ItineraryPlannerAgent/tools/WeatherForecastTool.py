from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import requests

api_key = os.getenv("OPENWEATHER_API_KEY")

class WeatherForecastTool(BaseTool):
    """
    Provides weather forecast data for a specified location using the OpenWeather API.
    """

    location: str = Field(
        ..., description="Location for which to retrieve the weather forecast, in the format 'City,CountryCode'."
    )

    def run(self):
        base_url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {
            "q": self.location,
            "appid": api_key,
            "units": "metric"
        }
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            forecast = response.json()
            return forecast
        else:
            return "Failed to retrieve weather forecast."