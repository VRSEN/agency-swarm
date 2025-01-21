from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import requests
import datetime
from .APIGW_python_sdk_2_0_5.apig_sdk import signer

class RequestAPI(BaseTool):
    '''
    执行API请求并将请求响应保存在文件中。
    '''
    method: str = Field(
        ...,
        # description="API的请求方法，只能是如下之一：GET/PUT/POST/DELETE/HEAD/PATCH",
        description="API的请求方法",
    )
    
    url: str = Field(
        ...,
        description="API的请求URL"
    )
    
    header: str = Field(
        default=None,
        description="API的请求头，默认为空"
    )

    body: str = Field(
        ...,
        description="API的请求体"
    )
    
    access_key: str = Field(
        ...,
        description="access_key"
    )
    
    secret_key: str = Field(
        ...,
        description="secret_key"
    )

    def run(self):
        sig = signer.Signer()
        sig.Key = self.access_key
        sig.Secret = self.secret_key
        
        r = signer.HttpRequest(self.method, self.url)
        r.headers = {"content-type": "application/json"}
        r.body = self.body
        
        try:
            sig.Sign(r)
        except Exception as e:
            print("Error signing API request: ", str(e))
        midstr = "://"
        print(f"METHOD: {r.method}, URL: {r.scheme + midstr + r.host + r.uri}, HEADERS: {r.headers}, DATA: {r.body}")
        resp = requests.request(r.method, r.scheme + "://" + r.host + r.uri, headers=r.headers, data=r.body)
        content = bytes.decode(resp.content)
        result_json = {
            "status_code": resp.status_code,
            "reason": resp.reason,
            "content": json.loads(content)
        }

        # name the result file
        now = datetime.datetime.now()
        formatted_time = now.strftime("%Y%m%d_%H%M%S")
        prefix = "context_"
        suffix = ".json"
        filename = f"{prefix}{formatted_time}{suffix}"

        # save the result to it
        file_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "files")
        relpath = os.path.join("api_results", filename)
        abspath = os.path.abspath(os.path.join(file_dir, relpath))
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        with open(abspath, "w", encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False, indent=4)

        # return the relative file path
        return relpath
