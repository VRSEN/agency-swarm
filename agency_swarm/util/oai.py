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
        if client is None:
            # Check if the API key is set
            api_key = openai.api_key or os.getenv("OPENAI_API_KEY")
            if api_key is None:
                raise ValueError(
                    "OpenAI API key is not set. Please set it using set_openai_key."
                )
            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api2.zhec.moe/v1",
                timeout=httpx.Timeout(600.0),
                max_retries=10,
                default_headers={"OpenAI-Beta": "assistants=v2"},
                http_client=httpx.Client(proxy="http://127.0.0.1:7890")
            )
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
