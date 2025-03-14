from typing import Any
from openai.types.beta.file_search_tool import FileSearch as OpenAIFileSearch
from openai.types.beta.file_search_tool import FileSearchTool
from pydantic import ValidationError


class FileSearchConfig(OpenAIFileSearch):
    pass


class FileSearch(FileSearchTool):
    def __init__(self, **data: Any) -> None:
        try:
            super().__init__(**data)
        except ValidationError:
            # sometimes openai API sends a different schema
            super().__init__(type="file_search")

    type: str = "file_search"
