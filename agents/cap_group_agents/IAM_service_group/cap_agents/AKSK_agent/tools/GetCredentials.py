from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class GetCredentials(BaseTool):


    def run(self):
        AKSK = {
            "AK": "SCARKXC0UUA3GH8QXRQJ",
            "SK": "U3BdbkibZVo9Ycegotq1AtLjnxN7CRtUt8XLUc3z"
        }
        return AKSK

