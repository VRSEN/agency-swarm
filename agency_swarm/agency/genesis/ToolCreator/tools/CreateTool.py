import os

from pydantic import Field

from agency_swarm.agency.genesis.util import change_directory
from agency_swarm.tools import BaseTool


class CreateTool(BaseTool):
    """This tool writes provided custom tool code to a file named after the tool."""

    agent_name: str = Field(
        ..., description="Name of the agent to create the tool for."
    )
    tool_name: str = Field(
        ...,
        description="Name of the tool class in camel case.",
        examples=["ExampleTool"],
    )
    tool_code: str = Field(
        ..., description="Complete tool code that should be written to the file."
    )
    agency_name: str = Field(
        None,
        description="Name of the agency. Defaults to the agency currently being created.",
    )

    def run(self):
        try:
            target_path = (
                self.agency_name
                and f"./{self.agency_name}"
                or self._shared_state.get("agency_path")
            )

            with change_directory(target_path):
                with change_directory(self.agent_name):
                    file_path = os.path.join("tools", f"{self.tool_name}.py")
                    with open(file_path, "w") as file:
                        file.write(self.tool_code)
            return f"Tool code successfully written to {file_path}."
        except Exception as e:
            return f"Error writing to file: {e}"


if __name__ == "__main__":
    tool = CreateTool(
        agent_name="TestAgent",
        tool_name="TestTool",
        tool_code="""from agency_swarm.tools import BaseTool
from pydantic import Field

class TestTool(BaseTool):
    \"\"\"A simple tool that returns a greeting.\"\"\"
    def run(self):
        return "Hello from TestTool!"
""",
        agency_name="MyAgency",
    )
    print(tool.run())
