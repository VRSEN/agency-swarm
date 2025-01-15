import os
import json
import requests
import datetime
from APIGW_python_sdk_2_0_5.apig_sdk import signer

class RequestAPI():
    access_key = "JBJIXGRWC4Y6NMPSULES"
    secret_key = "ZqU3pdR2D8iQGdrXaBIOGUGcaElhAnXpVU3ygNKj"
    url = "https://ecs.cn-east-3.myhuaweicloud.com/v1/ab7c37539c4440feab0917e311cb0981/cloudservers/flavors?availability_zone=cn-east-3a"
    def run(self):
        sig = signer.Signer()
        sig.Key = self.access_key
        sig.Secret = self.secret_key
        
        r = signer.HttpRequest("GET", self.url)
        r.headers = {"content-type": "application/json"}
        r.body = ""
        
        try:
            sig.Sign(r)
        except Exception as e:
            print("Error signing API request: ", str(e))
        resp = requests.request(r.method, r.scheme + "://" + r.host + r.uri, headers=r.headers, data=r.body)
        content = bytes.decode(resp.content)
        result_json = {
            "status_code": resp.status_code,
            "reason": resp.reason,
            "content": json.loads(content)
        }
        now = datetime.datetime.now()
        formatted_time = now.strftime("%Y%m%d_%H%M%S")
        prefix = "context_"
        suffix = ".json"
        filename = f"{prefix}{formatted_time}{suffix}"
        file_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "files")
        result_file_path = os.path.join("api_results", filename)
        with open(os.path.join(file_dir, result_file_path), "w", encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False, indent=4)
        return f'{{"result_file_path":"{result_file_path}"}}'

req = RequestAPI()
req.run()