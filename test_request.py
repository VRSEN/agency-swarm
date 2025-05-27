import requests
import sys
import threading

url1 = "http://127.0.0.1:7860/test1/get_completion"
url2 = "http://127.0.0.1:7860/test2/get_completion"
url3 = "http://127.0.0.1:7860/tool/ExampleTool"
url4 = "http://127.0.0.1:7860/tool/TestTool2"
payload1 = {
    "message": "say hi to test2",
    # "message": "Ask agent 2 what is 3+5",
    # "message": "Ask test2 agent to get latest commit again and return its exact response",
    "recipient_agent": "test1",
    "threads": {}
}
payload2 = {
    "message": "Get secret word",
}
payload3 = {
    "example_field": "Get secret word",
}
payload4 = {
    "example_field2": "Get secret word",
}

# 2+15:
# {"test1":{"test2":"thread_RBsMWo4rP9X1KSiOYzdqmSLB","test3":None},"main_thread":"thread_HuzhDFShRwkCIeQ7BOatqWWd"}
# 2+21:
# {"test1":{"test2":"thread_f1ESiLxhF9OU3MNe67QXw50L","test3":None},"main_thread":"thread_loP42T4oT6btEWyZjkHwlLim"}

# {"test1":{"test2":null,"test3":null},"main_thread":"thread_vjdkW3p2mVHADS1GBdrT8Baq"}

data = [
    (url1, payload1), 
    # (url2, payload2), 
    # (url3, payload3), 
    # (url4, payload4)
]

headers = {
    "Authorization": "Bearer 123",
    # "Accept-Encoding": "identity"  # Disable compression to avoid buffering
}

def post_request_stream(url, payload):
    resp = requests.post(url, json=payload, headers=headers, stream=True)
    print(f"URL: {url}")
    print("Status code:", resp.status_code)
    print("Streaming response:")
    try:
        for chunk in resp.iter_content(chunk_size=None):
            if chunk:
                try:
                    print(f"{url.split('/')[3]}: {chunk.decode('utf-8')}", end='', flush=True)
                    sys.stdout.flush()
                except Exception as e:
                    print(f"\nFailed to decode chunk: {e}")
        print()  # for newline after stream
    except Exception as e:
        print("Failed during streaming:", e)

threads = []
for url, payload in data:
    t = threading.Thread(target=post_request_stream, args=(url, payload))
    t.start()
    threads.append(t)

for t in threads:
    t.join()