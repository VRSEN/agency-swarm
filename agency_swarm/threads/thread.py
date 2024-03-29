import inspect
import time
from typing import Literal

from openai import BadRequestError

from agency_swarm.util.streaming import AgencyEventHandler
from agency_swarm.agents import Agent
from agency_swarm.messages import MessageOutput
from agency_swarm.user import User
from agency_swarm.util.oai import get_openai_client


class Thread:
    id: str = None
    thread = None
    run = None
    stream = None

    def __init__(self, agent: Literal[Agent, User], recipient_agent: Agent):
        self.agent = agent
        self.recipient_agent = recipient_agent

        self.client = get_openai_client()

    def init_thread(self):
        if self.id:
            self.thread = self.client.beta.threads.retrieve(self.id)
        else:
            self.thread = self.client.beta.threads.create()
            self.id = self.thread.id

    def get_completion_stream(self, message: str, event_handler: type(AgencyEventHandler), message_files=None, recipient_agent=None):
        return self.get_completion(message, message_files, False, recipient_agent, event_handler)

    def get_completion(self, message: str, message_files=None, yield_messages=True, recipient_agent=None,
                       event_handler: type(AgencyEventHandler) = None):
        if not self.thread:
            self.init_thread()

        if not recipient_agent:
            recipient_agent = self.recipient_agent

        if event_handler:
            yield_messages = False
            event_handler.agent_name = self.agent.name
            event_handler.recipient_agent_name = recipient_agent.name

        # Determine the sender's name based on the agent type
        sender_name = "user" if isinstance(self.agent, User) else self.agent.name
        playground_url = f'https://platform.openai.com/playground?assistant={recipient_agent.assistant.id}&mode=assistant&thread={self.thread.id}'
        print(f'THREAD:[ {sender_name} -> {recipient_agent.name} ]: URL {playground_url}')

        # send message
        self.client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=message,
            file_ids=message_files if message_files else [],
        )

        if yield_messages:
            yield MessageOutput("text", self.agent.name, recipient_agent.name, message)

        self._create_run(recipient_agent, event_handler)

        run_failed = False
        while True:
            self._run_until_done()

            # function execution
            if self.run.status == "requires_action":
                tool_calls = self.run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                for tool_call in tool_calls:
                    if yield_messages:
                        yield MessageOutput("function", recipient_agent.name, self.agent.name,
                                            str(tool_call.function))

                    output = self.execute_tool(tool_call, recipient_agent, event_handler)
                    if inspect.isgenerator(output):
                        try:
                            while True:
                                item = next(output)
                                if isinstance(item, MessageOutput) and yield_messages:
                                    yield item
                        except StopIteration as e:
                            output = e.value
                            if event_handler:
                                event_handler.agent_name = self.agent.name
                                event_handler.recipient_agent_name = recipient_agent.name
                    else:
                        if yield_messages:
                            yield MessageOutput("function_output", tool_call.function.name, recipient_agent.name,
                                                output)

                    tool_outputs.append({"tool_call_id": tool_call.id, "output": str(output)})

                # submit tool outputs
                try:
                    self._submit_tool_outputs(tool_outputs, event_handler)
                except BadRequestError as e:
                    if 'Runs in status "expired"' in e.message:
                        self.client.beta.threads.messages.create(
                            thread_id=self.thread.id,
                            role="user",
                            content="Please repeat the exact same function calls again in the same order."
                        )

                        self._create_run(recipient_agent, event_handler)

                        self._run_until_done()

                        if self.run.status != "requires_action":
                            raise Exception("Run Failed. Error: ", self.run.last_error)

                        # change tool call ids
                        tool_calls = self.run.required_action.submit_tool_outputs.tool_calls
                        for i, tool_call in enumerate(tool_calls):
                            tool_outputs[i]["tool_call_id"] = tool_call.id

                        self._submit_tool_outputs(tool_outputs, event_handler)
                    else:
                        raise e
            # error
            elif self.run.status == "failed":
                # retry run 1 time
                if not run_failed and "something went wrong" in self.run.last_error:
                    self._create_run(recipient_agent, event_handler)
                    run_failed = True
                else:
                    raise Exception("Run Failed. Error: ", self.run.last_error)
            # return assistant message
            else:
                messages = self.client.beta.threads.messages.list(
                    thread_id=self.id
                )
                message = messages.data[0].content[0].text.value

                if yield_messages:
                    yield MessageOutput("text", recipient_agent.name, self.agent.name, message)

                return message

    def _create_run(self, recipient_agent, event_handler):
        if event_handler:
            with self.client.beta.threads.runs.create_and_stream(
                thread_id=self.thread.id,
                event_handler=event_handler(),
                assistant_id=recipient_agent.id
            ) as stream:
                stream.until_done()
                self.run = stream.get_final_run()
        else:
            self.run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=recipient_agent.id,
            )

    def _run_until_done(self):
        while self.run.status in ['queued', 'in_progress', "cancelling"]:
            time.sleep(0.5)
            self.run = self.client.beta.threads.runs.retrieve(
                thread_id=self.thread.id,
                run_id=self.run.id
            )

    def _submit_tool_outputs(self, tool_outputs, event_handler):
        if not event_handler:
            self.run = self.client.beta.threads.runs.submit_tool_outputs(
                thread_id=self.thread.id,
                run_id=self.run.id,
                tool_outputs=tool_outputs
            )
        else:
            with self.client.beta.threads.runs.submit_tool_outputs_stream(
                    thread_id=self.thread.id,
                    run_id=self.run.id,
                    tool_outputs=tool_outputs,
                    event_handler=event_handler()
            ) as stream:
                stream.until_done()
                self.run = stream.get_final_run()

    def execute_tool(self, tool_call, recipient_agent=None, event_handler=None):
        if not recipient_agent:
            recipient_agent = self.recipient_agent

        funcs = recipient_agent.functions
        func = next((func for func in funcs if func.__name__ == tool_call.function.name), None)

        if not func:
            return f"Error: Function {tool_call.function.name} not found. Available functions: {[func.__name__ for func in funcs]}"

        try:
            # init tool
            func = func(**eval(tool_call.function.arguments))
            func.caller_agent = recipient_agent
            func.event_handler = event_handler
            # get outputs from the tool
            output = func.run()

            return output
        except Exception as e:
            error_message = f"Error: {e}"
            if "For further information visit" in error_message:
                error_message = error_message.split("For further information visit")[0]
            return error_message