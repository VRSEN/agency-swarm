import time
from typing import Literal

from agency_swarm.agents import BaseAgent
from agency_swarm.messages import MessageOutput
from agency_swarm.user import User
from agency_swarm.util.oai import get_openai_client


class Thread:
    id: str
    thread = None
    run = None

    def __init__(self, agent: Literal[BaseAgent, User], recipient_agent: BaseAgent):
        self.agent = agent
        self.recipient_agent = recipient_agent
        self.client = get_openai_client()

    def get_completion(self, message: str):
        if not self.thread:
            self.thread = self.client.beta.threads.create()
            self.id = self.thread.id

        # send message
        self.client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=message
        )
        yield MessageOutput("text", self.agent.name, self.recipient_agent.name, message)

        # create run
        self.run = self.client.beta.threads.runs.create(
            thread_id=self.thread.id,
            assistant_id=self.recipient_agent.id,
        )

        while True:
            # wait until run completes
            while self.run.status in ['queued', 'in_progress']:
                time.sleep(0.5)
                self.run = self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread.id,
                    run_id=self.run.id
                )

            # function execution
            if self.run.status == "requires_action":
                tool_calls = self.run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                for tool_call in tool_calls:
                    yield MessageOutput("function", self.recipient_agent.name, self.agent.name, str(tool_call.function))

                    # handle special case for send message tool that uses yield
                    if tool_call.function.name == "SendMessage":
                        gen = self._execute_tool(tool_call)
                        try:
                            while True:
                                yield next(gen)
                        except StopIteration as e:
                            output = e.value
                    else:
                        output = self._execute_tool(tool_call)
                        yield MessageOutput("function_output", tool_call.function.name, self.agent.name, output)

                    tool_outputs.append({"tool_call_id": tool_call.id, "output": output})

                # submit tool outputs
                self.run = self.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=self.thread.id,
                    run_id=self.run.id,
                    tool_outputs=tool_outputs
                )
            # error
            elif self.run.status == "failed":
                raise Exception("Run Failed. Error: ", self.run.last_error)
            # return assistant message
            else:
                messages = self.client.beta.threads.messages.list(
                    thread_id=self.id
                )
                message = messages.data[0].content[0].text.value
                yield MessageOutput("text", self.recipient_agent.name, self.agent.name, message)
                return message

    def _execute_tool(self, tool_call):
        funcs = self.recipient_agent.functions
        func = next(iter([func for func in funcs if func.__name__ == tool_call.function.name]))

        try:
            # init tool
            func = func(**eval(tool_call.function.arguments))
            # get outputs from the tool
            output = func.run()

            return output
        except Exception as e:
            return "Error: " + str(e)
