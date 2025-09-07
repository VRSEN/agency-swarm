"""
Tools Demo (BaseTool and @function_tool)

Implement the same Add operation two ways: BaseTool and @function_tool, each
with field and model validators.

Run with: python examples/tools.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from pydantic import BaseModel, Field, field_validator, model_validator

# Add src to path for standalone example execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent, BaseTool, ModelSettings, function_tool  # noqa: E402  # isort: skip


# --- BaseTool pattern --- #


class AddTool(BaseTool):
    """Add two non-negative integers.

    :param a: First addend (>= 0, <= 100)
    :param b: Second addend (>= 0, <= 100)
    :returns: Sum as a string. The sum must be <= 100.
    """

    a: int = Field(..., ge=0, description="First addend (>= 0)")
    b: int = Field(..., ge=0, description="Second addend (>= 0)")

    @field_validator("a", "b")
    @classmethod
    def cap_each_value(cls, v: int) -> int:
        if v > 100:
            raise ValueError("each value must be <= 100")
        return v

    @model_validator(mode="after")
    def cap_sum(self) -> AddTool:
        if self.a + self.b > 100:
            raise ValueError("sum must be <= 100")
        return self

    class ToolConfig:
        strict: bool = True

    def run(self) -> str:
        return str(self.a + self.b)


# --- @function_tool pattern --- #


class AddArgs(BaseModel):
    a: int = Field(..., ge=0, description="First addend (>= 0)")
    b: int = Field(..., ge=0, description="Second addend (>= 0)")

    @field_validator("a", "b")
    @classmethod
    def cap_each_value(cls, v: int) -> int:
        if v > 100:
            raise ValueError("each value must be <= 100")
        return v

    @model_validator(mode="after")
    def cap_sum(self) -> AddArgs:
        if self.a + self.b > 100:
            raise ValueError("sum must be <= 100")
        return self


@function_tool
def add_numbers(args: AddArgs) -> str:
    """Add two non-negative integers.

    :returns: Sum as a string. The sum must be <= 100.
    """
    return str(args.a + args.b)


def create_demo_agency() -> Agency:
    tool_user = Agent(
        name="ToolDemo",
        instructions=(
            "You can add integers using two tools: add_numbers (function tool) and AddTool (BaseTool). "
            "When asked to add numbers, use the specified tool. Respond strictly as either 'Result: <sum>' "
            "or 'Error: <reason>'."
        ),
        tools=[add_numbers, AddTool],
        model_settings=ModelSettings(temperature=0.0),
    )
    return Agency(tool_user)


agency = create_demo_agency()


async def run_demo() -> None:
    # FunctionTool: valid inputs
    r1 = await agency.get_response("Add 2 and 3 using add_numbers.")
    print(r1.final_output)

    # BaseTool: invalid inputs (sum exceeds 100)
    r2 = await agency.get_response("Add 70 and 50 using AddTool.")
    print(r2.final_output)


if __name__ == "__main__":
    asyncio.run(run_demo())
