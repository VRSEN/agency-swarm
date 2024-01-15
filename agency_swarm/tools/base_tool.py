from abc import ABC, abstractmethod

from instructor import OpenAISchema


class BaseTool(OpenAISchema, ABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @abstractmethod
    def run(self, **kwargs):
        pass
