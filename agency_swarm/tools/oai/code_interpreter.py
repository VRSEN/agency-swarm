from pydantic import BaseModel


class CodeInterpreter(BaseModel):
    type: str = "code_interpreter"
