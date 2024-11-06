import os
import threading

import httpx
import openai
from dotenv import load_dotenv

load_dotenv()

client_lock = threading.Lock()
client = None


def get_openai_client():
    global client
    with client_lock:
        if client is not None:
            return client

        # Check if the API key is set
        api_key = openai.api_key or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key is not set. Please set it using set_openai_key.")

        # OpenAI client configuration
        client_params = {
            'api_key': api_key,
            'timeout': httpx.Timeout(60.0, read=40, connect=5.0),
            'max_retries': 10,
            'default_headers': {"OpenAI-Beta": "assistants=v2"},
        }

        # Check for Helicone key
        helicone_key = os.getenv("HELICONE_API_KEY")
        if helicone_key:
            client_params['base_url'] = "https://oai.hconeai.com/v1"
            client_params['default_headers']["Helicone-Auth"] = f"Bearer {helicone_key}"

        client = openai.OpenAI(**client_params)

    return client


def set_openai_client(new_client):
    global client
    with client_lock:
        client = new_client


def set_openai_key(key):
    if not key:
        raise ValueError("Invalid API key. The API key cannot be empty.")
    openai.api_key = key
    global client
    with client_lock:
        client = None
