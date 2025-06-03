"""
Test script that sends a test request to an endpoint created within the fastapi_demo.py file.

Use this to verify that your FastAPI tool endpoints are working correctly.

Usage:
    python fastapi_request_demo.py
"""

import requests
from requests.exceptions import ConnectionError

AGENCY_ENDPOINT = "http://localhost:7860/test_agency/get_completion"
TOOL_ENDPOINT = "http://localhost:7860/tool/ExampleTool"
BEARER_TOKEN = "123"

headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}

def send_completion_request():
    try:
        data = {"message": "Hello, how are you doing?"}
        response = requests.post(AGENCY_ENDPOINT, json=data, headers=headers)
        print(f"Completion response: {response.text}")
    except ConnectionError:
        print("Could not connect to the server, please run fastapi_demo.py prior to running this script.")
    except Exception as e:
        print(f"Error: {e}")

def send_tool_request():
    try:
        data = {"input": "Test input"}
        response = requests.post(TOOL_ENDPOINT, json=data, headers=headers)
        print(f"Tool response: {response.text}")
    except ConnectionError:
        print("Could not connect to the server, please run fastapi_demo.py prior to running this script.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    send_completion_request()
    send_tool_request()
