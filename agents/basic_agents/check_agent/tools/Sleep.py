from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import time
import random


class Sleep(BaseTool):

    def run(self):
        for i in range(5):
            time.sleep(2)
        return 
