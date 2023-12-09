from abc import ABC, abstractmethod
from instructor import OpenAISchema
from termcolor import colored


class AsyncBaseTool(OpenAISchema, ABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @abstractmethod
    async def run(self, **kwargs):
        pass
