from openai import OpenAI
from typing import Callable
from pydantic import Field, BaseModel
from agency_swarm.util.oai import get_openai_client

class Validator(BaseModel):
    """
    Validate if an attribute is correct and if not,
    return a new value with an error message
    """
    reason: str = Field(..., description="Step-by-step reasoning why the attribute could be valid or not with a conclussion at the end.")
    is_valid: bool = Field(..., description="Whether the attribute is valid based on the requirements.")
    fixed_value: str = Field(..., description="If the attribute is not valid, suggest a new value for the attribute. Otherwise, leave it empty.")

def llm_validator(
    statement: str,
    client: OpenAI=None,
    allow_override: bool = False,
    model: str = "gpt-4o-mini",
    temperature: float = 0,
) -> Callable[[str], str]:
    """
    Create a validator that uses the LLM to validate an attribute

    ## Usage

    ```python
    from agency_swarm import llm_validator
    from pydantic import Field, field_validator

    class User(BaseTool):
        name: str = Annotated[str, llm_validator("The name must be a full name all lowercase")
        age: int = Field(description="The age of the person")

    try:
        user = User(name="Jason Liu", age=20)
    except ValidationError as e:
        print(e)
    ```

    ```
    1 validation error for User
    name
        The name is valid but not all lowercase (type=value_error.llm_validator)
    ```

    Note that there, the error message is written by the LLM, and the error type is `value_error.llm_validator`.

    Parameters:
        statement (str): The statement to validate
        model (str): The LLM to use for validation. Must be compatible with structured outputs. (default: "gpt-4o-mini")
        temperature (float): The temperature to use for the LLM (default: 0)
        openai_client (OpenAI): The OpenAI client to use (default: None)
    """
    if client is None:
        client = get_openai_client()

    def llm(v: str) -> str:
        resp = client.beta.chat.completions.parse(
            response_format=Validator,
            messages=[
                {
                    "role": "system",
                    "content": "You are a world class validation model, capable to determine if the following value is valid or not for a given statement. Before providing a response, you must think step by step about the validation.",
                },
                {
                    "role": "user",
                    "content": f"Does `{v}` follow the rules: {statement}",
                },
            ],
            model=model,
            temperature=temperature,
        )

        if resp.choices[0].message.refusal:
            raise ValueError(resp.choices[0].message.refusal)

        resp = resp.choices[0].message.parsed

        # If the response is  not valid, return the reason, this could be used in
        # the future to generate a better response, via reasking mechanism.
        assert resp.is_valid, resp.reason

        if allow_override and not resp.is_valid and resp.fixed_value is not None:
            # If the value is not valid, but we allow override, return the fixed value
            return resp.fixed_value
        return v

    return llm