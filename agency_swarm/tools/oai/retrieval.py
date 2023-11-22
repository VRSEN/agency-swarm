from pydantic import BaseModel


class Retrieval(BaseModel):
    type: str = "retrieval"