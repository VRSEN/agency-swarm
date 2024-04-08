from pydantic import Field

from agency_swarm import BaseTool


class CheckCurrentDir(BaseTool):
    """
    This tool checks the current directory path.
    """
    chain_of_thought: str = Field(
        ...,
        description="Please think step-by-step about what you need to do next, after checking current directory to solve the task.",
        exclude=True,
    )
    one_call_at_a_time: bool = True

    def run(self):
        import os

        return os.getcwd()
