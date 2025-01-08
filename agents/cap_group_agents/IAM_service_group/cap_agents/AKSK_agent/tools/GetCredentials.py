from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class GetCredentials(BaseTool):


    def run(self):
        AKSK = {
            "AK": "",
            "SK": ""
        }
        return AKSK

