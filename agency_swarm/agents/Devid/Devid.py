from typing_extensions import override
import re
from agency_swarm.agents import Agent
from agency_swarm.tools import Retrieval
from instructor import llm_validator


class Devid(Agent):
    def __init__(self):
        super().__init__(
            name="Devid",
            description="Devid is an AI software engineer capable of performing advanced coding tasks.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[Retrieval],
            tools_folder="./tools",
            validation_attempts=1,
        )

    @override
    def response_validator(self, message):
        pattern = r'(```)((.*\n){5,})(```)'

        if re.search(pattern, message):
            # take only first 100 characters
            raise ValueError(
                "You returned code snippet. Please never return code snippets to me. "
                "Use the FileWriter tool to write the code locally. Then, test it if possible. Continue."
            )

        llm_validator(statement="Verify whether the update from the AI Developer Agent confirms the task's "
                                "successful completion. If the task remains unfinished, provide guidance "
                                "within the 'reason' argument on the next steps the agent should take. For "
                                "instance, if the agent encountered an error, advise the inclusion of debug "
                                "statements for another attempt. Should the agent outline potential "
                                "solutions or further actions, direct the agent to execute those plans. "
                                "Message does not have to contain code snippets. Just confirmation.",
                      openai_client=self.client)(message)

        return message
