from typing import Optional
from pydantic import BaseModel, field_validator, Field

class FileSearchConfig(BaseModel):
    max_num_results: int = Field(50, description="Optional override for the maximum number of results")

    @field_validator('max_num_results')
    def check_max_num_results(cls, v):
        if not 1 <= v <= 50:
            raise ValueError('file_search.max_num_results must be between 1 and 50 inclusive')
        return v
class FileSearch(BaseModel):
    type: str = "file_search"

    file_search: Optional[FileSearchConfig] = None

    class Config:
        exclude_none = True
