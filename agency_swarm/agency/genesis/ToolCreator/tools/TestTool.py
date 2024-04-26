import os
from typing import Optional

from pydantic import Field, model_validator

from agency_swarm.agency.genesis.util import check_agency_path
from agency_swarm.tools import BaseTool, ToolFactory


class TestTool(BaseTool):
    """
    This tool tests other tools defined in tools.py file with the given arguments. Make sure to define the run method before testing.
    """
    agent_name: str = Field(
        ..., description="Name of the agent to test the tool for."
    )
    chain_of_thought: str = Field(
        ..., description="Think step by step to determine the correct arguments for testing.", exclude=True
    )
    tool_name: str = Field(..., description="Name of the tool to be run.")
    arguments: Optional[str] = Field(...,
                                     description="Arguments to be passed to the tool for testing "
                                                 "in serialized JSON format.")
    agency_name: str = Field(
        None, description="Name of the agency to create the tool for. Defaults to the agency currently being created."
    )

    def run(self):
        if self.agency_name:
            os.chdir("./" + self.agency_name)
        else:
            os.chdir(self.shared_state.get("agency_path"))
        os.chdir(self.agent_name)

        # import tool by self.tool_name from local tools.py file
        try:
            tool = ToolFactory.from_file(f"./tools/{self.tool_name}.py")
        except Exception as e:
            raise ValueError(f"Error importing tool {self.tool_name}: {e}")
        finally:
            os.chdir(self.shared_state.get("default_folder"))

        try:
            if not self.arguments:
                output = tool().run()
            else:
                output = tool(**eval(self.arguments)).run()
        except Exception as e:
            raise ValueError(f"Error running tool {self.tool_name}: {e}")
        finally:
            os.chdir(self.shared_state.get("default_folder"))

        if not output:
            raise ValueError(f"Tool {self.tool_name} did not return any output.")

        return f"Successfully initialized and ran tool. Output: '{output}'"

    @model_validator(mode="after")
    def validate_tool_name(self):
        check_agency_path(self)

        if not self.agent_name and not self.shared_state.get("agent_name"):
            raise ValueError("Please provide agent name.")

        agent_name = self.agent_name or self.shared_state.get("agent_name")

        tool_path = os.path.join(self.shared_state.get("agency_path"), agent_name)
        tool_path = os.path.join(str(tool_path), "tools")
        tool_path = os.path.join(tool_path, self.tool_name + ".py")


        # check if tools.py file exists
        if not os.path.isfile(tool_path):
            available_tools = os.listdir(os.path.join(self.shared_state.get("agency_path"), agent_name))
            available_tools = [tool for tool in available_tools if tool.endswith(".py")]
            available_tools = [tool for tool in available_tools if
                               not tool.startswith("__") and not tool.startswith(".")]
            available_tools = [tool.replace(".py", "") for tool in available_tools]
            available_tools = ", ".join(available_tools)
            raise ValueError(f"Tool {self.tool_name} not found. Available tools are: {available_tools}")

        agent_path = os.path.join(self.shared_state.get("agency_path"), self.agent_name)
        if not os.path.exists(agent_path):
            available_agents = os.listdir(self.shared_state.get("agency_path"))
            available_agents = [agent for agent in available_agents if
                                os.path.isdir(os.path.join(self.shared_state.get("agency_path"), agent))]
            raise ValueError(f"Agent {self.agent_name} not found. Available agents are: {available_agents}")

        return True


if __name__ == "__main__":
    TestTool.shared_state.data = {"agency_path": "/Users/vrsen/Projects/agency-swarm/agency-swarm/TestAgency",
                              "default_folder": "/Users/vrsen/Projects/agency-swarm/agency-swarm/TestAgency"}
    test_tool = TestTool(agent_name="TestAgent", tool_name="PrintTestTool", arguments="{}", chain_of_thought="")
    print(test_tool.run())
