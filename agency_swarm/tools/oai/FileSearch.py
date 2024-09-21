from typing import Optional
from pydantic import BaseModel, field_validator, Field
from typing import Dict, Union, Optional

class FileSearchConfig(BaseModel):
    max_num_results: int = Field(50, description="Optional override for the maximum number of results")
    ranking_options: Optional[Dict[str, Union[str, float]]] = Field(
        {'ranker': 'default_2024_08_21', 'score_threshold': 0.0},
        description="The ranking options for the file search. If not specified, the file search tool will use the auto ranker and a score_threshold of 0."
    )

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
