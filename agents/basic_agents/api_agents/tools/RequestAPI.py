from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import requests
from .APIGW_python_sdk_2_0_5.apig_sdk import signer

class RequestAPI(BaseTool):
    '''
    执行API请求并返回请求响应。
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
        resp = requests.request(r.method, r.scheme + "://" + r.host + r.uri, headers=r.headers, data=r.body)
        content = bytes.decode(resp.content)
        return_obj = {
            "status_code": resp.status_code,
            "reason": resp.reason,
            "content": json.loads(content)
        }
        return json.dumps(return_obj, ensure_ascii=False)
