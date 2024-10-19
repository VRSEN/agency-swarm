import httpx
import openai
import threading
import os

from astra_assistants import patch
from openai.types.chat_model import ChatModel

from dotenv import load_dotenv

load_dotenv()

client_lock = threading.Lock()
client = None


def get_openai_client(model:str=None):
    global client
    with client_lock:
        if client is None:
            # Check if the API key is set
            api_key = openai.api_key or os.getenv('OPENAI_API_KEY')
            if api_key is None:
                raise ValueError("OpenAI API key is not set. Please set it using set_openai_key.")
            client = openai.OpenAI(api_key=api_key,
                                   timeout=httpx.Timeout(60.0, read=40, connect=5.0),
                                   max_retries=10,
                                   default_headers={"OpenAI-Beta": "assistants=v2"})
            if model is not None and model not in ChatModel:
                print(f"Using astra-assistants for non OpenAI model {model}, note thread URLs will not work.")
                client = patch(client)
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
