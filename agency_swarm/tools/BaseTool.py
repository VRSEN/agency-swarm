from abc import ABC, abstractmethod

from instructor import OpenAISchema


class BaseTool(OpenAISchema, ABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # # Exclude 'run' method from Pydantic model fields
        # self.model_fields.pop("run", None)

    @abstractmethod
    def run(self, **kwargs):
        pass
