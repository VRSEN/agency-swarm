from openai.types.beta.file_search_tool import FileSearch as OpenAIFileSearch
from openai.types.beta.file_search_tool import FileSearchTool


class FileSearchConfig(OpenAIFileSearch):
    pass


class FileSearch(FileSearchTool):
    type: str = "file_search"
