from pydantic import BaseModel


class FileSearch(BaseModel):
    type: str = "file_search"