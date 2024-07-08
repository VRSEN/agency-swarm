import inspect
import json
import time
from typing import List, Optional, Union

from openai import BadRequestError
from openai.types.beta import AssistantToolChoice
from openai.types.beta.threads.message import Attachment
from openai.types.beta.threads.run import TruncationStrategy

from agency_swarm.tools import FileSearch, CodeInterpreter
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

    def __init__(self, agent: Union[Agent, User], recipient_agent: Agent):
        self.agent = agent
        self.recipient_agent = recipient_agent

        self.client = get_openai_client()

    def init_thread(self):
        if self.id:
            self.thread = self.client.beta.threads.retrieve(self.id)
        else:
            self.thread = self.client.beta.threads.create()
            self.id = self.thread.id

            if self.recipient_agent.examples:
                for example in self.recipient_agent.examples:
                    self.client.beta.threads.messages.create(
                        thread_id=self.id,
                        **example,
                    )

    def get_completion_stream(self,
                              message: str,
                              event_handler: type(AgencyEventHandler),
                              message_files: List[str] = None,
                              attachments: Optional[List[Attachment]] = None,
                              recipient_agent=None,
                              additional_instructions: str = None,
                              tool_choice: AssistantToolChoice = None):

        return self.get_completion(message,
                                   message_files,
                                   attachments,
                                   recipient_agent,
                                   additional_instructions,
                                   event_handler,
                                   tool_choice,
                                   yield_messages=False)

    def get_completion(self,
                       message: str | List[dict],
                       message_files: List[str] = None,
                       attachments: Optional[List[dict]] = None,
                       recipient_agent=None,
                       additional_instructions: str = None,
                       event_handler: type(AgencyEventHandler) = None,
                       tool_choice: AssistantToolChoice = None,
                       yield_messages: bool = False
                       ):
        if not recipient_agent:
            recipient_agent = self.recipient_agent

        if not attachments:
            attachments = []

        if message_files:
            recipient_tools = []

            if FileSearch in recipient_agent.tools:
                recipient_tools.append({"type": "file_search"})
            if CodeInterpreter in recipient_agent.tools:
                recipient_tools.append({"type": "code_interpreter"})

            for file_id in message_files:
                attachments.append({"file_id": file_id,
                                    "tools": recipient_tools or [{"type": "file_search"}]})

        if not self.thread:
            self.init_thread()

        if event_handler:
            event_handler.set_agent(self.agent)
            event_handler.set_recipient_agent(recipient_agent)

        # Determine the sender's name based on the agent type
        sender_name = "user" if isinstance(self.agent, User) else self.agent.name
        playground_url = f'https://platform.openai.com/playground/assistants?assistant={recipient_agent.assistant.id}&mode=assistant&thread={self.thread.id}'
        print(f'THREAD:[ {sender_name} -> {recipient_agent.name} ]: URL {playground_url}')

        # send message
        message_obj = self.client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=message,
            attachments=attachments
        )

        if yield_messages:
            yield MessageOutput("text", self.agent.name, recipient_agent.name, message, message_obj)

        self._create_run(recipient_agent, additional_instructions, event_handler, tool_choice)

        error_attempts = 0
        validation_attempts = 0
        full_message = ""
        while True:
            self._run_until_done()

            # function execution
            if self.run.status == "requires_action":
                tool_calls = self.run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                tool_names = []
                for tool_call in tool_calls:
                    if yield_messages:
                        yield MessageOutput("function", recipient_agent.name, self.agent.name,
                                            str(tool_call.function), tool_call)

                    output = self.execute_tool(tool_call, recipient_agent, event_handler, tool_names)

                    if inspect.isgenerator(output):
                        try:
                            while True:
                                item = next(output)
                                if isinstance(item, MessageOutput) and yield_messages:
                                    yield item
                        except StopIteration as e:
                            output = e.value
                    else:
                        if yield_messages:
                            yield MessageOutput("function_output", tool_call.function.name, recipient_agent.name,
                                                output, tool_call)

                    if event_handler:
                        event_handler.set_agent(self.agent)
                        event_handler.set_recipient_agent(recipient_agent)

                    tool_outputs.append({"tool_call_id": tool_call.id, "output": str(output)})
                    tool_names.append(tool_call.function.name)

                # submit tool outputs
                try:
                    self._submit_tool_outputs(tool_outputs, event_handler)
                except BadRequestError as e:
                    if 'Runs in status "expired"' in e.message:
                        self.client.beta.threads.messages.create(
                            thread_id=self.thread.id,
                            role="user",
                            content="Previous request timed out. Please repeat the exact same tool calls in the same order with the same arguments."
                        )

                        self._create_run(recipient_agent, additional_instructions, event_handler, 'required',
                                         temperature=0)

                        self._run_until_done()

                        if self.run.status != "requires_action":
                            raise Exception("Run Failed. Error: ", self.run.last_error)

                        # change tool call ids
                        tool_calls = self.run.required_action.submit_tool_outputs.tool_calls

                        if len(tool_calls) != len(tool_outputs):
                            tool_outputs = []
                            for i, tool_call in enumerate(tool_calls):
                                tool_outputs.append({"tool_call_id": tool_call.id,
                                                     "output": "Error: openai run timed out. You can try again one more time."})
                        else:
                            for i, tool_name in enumerate(tool_names):
                                for tool_call in tool_calls[:]:
                                    if tool_call.function.name == tool_name:
                                        tool_outputs[i]["tool_call_id"] = tool_call.id
                                        tool_calls.remove(tool_call)
                                        break

                        self._submit_tool_outputs(tool_outputs, event_handler)
                    else:
                        raise e
            # error
            elif self.run.status == "failed":
                full_message += self._get_last_message_text()
                # retry run 2 times
                if error_attempts < 1 and "something went wrong" in self.run.last_error.message.lower():
                    time.sleep(1)
                    self._create_run(recipient_agent, additional_instructions, event_handler, tool_choice)
                    error_attempts += 1
                if (
                    error_attempts < 1
                    and "rate limit reached" in self.run.last_error.message.lower()
                ):
                    time.sleep(60)
                    self._create_run(
                        recipient_agent,
                        additional_instructions,
                        event_handler,
                        tool_choice,
                    )
                    error_attempts += 1
                elif (
                    1 <= error_attempts < 10
                    and "something went wrong" in self.run.last_error.message.lower()
                ):
                    self.client.beta.threads.messages.create(
                        thread_id=self.thread.id,
                        role="user",
                        content="Continue."
                    )
                    self._create_run(recipient_agent, additional_instructions, event_handler, tool_choice)
                    error_attempts += 1
                elif (
                    1 <= error_attempts < 10
                    and "rate limit reached" in self.run.last_error.message.lower()
                ):
                    time.sleep(60)
                    self.client.beta.threads.messages.create(
                        thread_id=self.thread.id, role="user", content="Continue."
                    )
                    self._create_run(
                        recipient_agent,
                        additional_instructions,
                        event_handler,
                        tool_choice,
                    )
                    error_attempts += 1
                else:
                    raise Exception("OpenAI Run Failed. Error: ", self.run.last_error.message)
            # return assistant message
            else:
                message_obj = self._get_last_assistant_message()
                last_message = message_obj.content[0].text.value
                full_message += last_message

                if yield_messages:
                    yield MessageOutput("text", recipient_agent.name, self.agent.name, full_message, message_obj)

                if recipient_agent.response_validator:
                    try:
                        if isinstance(recipient_agent, Agent):
                            recipient_agent.response_validator(message=last_message)
                    except Exception as e:
                        if validation_attempts < recipient_agent.validation_attempts:
                            try:
                                evaluated_content = eval(str(e))
                                if isinstance(evaluated_content, list):
                                    content = evaluated_content
                                else:
                                    content = str(e)
                            except Exception as eval_exception:
                                content = str(e)

                            message_obj = self.client.beta.threads.messages.create(
                                thread_id=self.thread.id,
                                role="user",
                                content=content,
                            )

                            if yield_messages:
                                for content in message_obj.content:
                                    if hasattr(content, 'text') and hasattr(content.text, 'value'):
                                        yield MessageOutput("text", self.agent.name, recipient_agent.name,
                                                            content.text.value, message_obj)
                                        break

                            if event_handler:
                                handler = event_handler()
                                handler.on_message_created(message_obj)
                                handler.on_message_done(message_obj)

                            validation_attempts += 1

                            self._create_run(recipient_agent, additional_instructions, event_handler, tool_choice)

                            continue

                return full_message

    def _create_run(self, recipient_agent, additional_instructions, event_handler, tool_choice, temperature=None):
        if event_handler:
            with self.client.beta.threads.runs.stream(
                    thread_id=self.thread.id,
                    event_handler=event_handler(),
                    assistant_id=recipient_agent.id,
                    additional_instructions=additional_instructions,
                    tool_choice=tool_choice,
                    max_prompt_tokens=recipient_agent.max_prompt_tokens,
                    max_completion_tokens=recipient_agent.max_completion_tokens,
                    truncation_strategy=recipient_agent.truncation_strategy,
                    temperature=temperature
            ) as stream:
                stream.until_done()
                self.run = stream.get_final_run()
        else:
            self.run = self.client.beta.threads.runs.create_and_poll(
                thread_id=self.thread.id,
                assistant_id=recipient_agent.id,
                additional_instructions=additional_instructions,
                tool_choice=tool_choice,
                max_prompt_tokens=recipient_agent.max_prompt_tokens,
                max_completion_tokens=recipient_agent.max_completion_tokens,
                truncation_strategy=recipient_agent.truncation_strategy,
                temperature=temperature
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
            self.run = self.client.beta.threads.runs.submit_tool_outputs_and_poll(
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

    def _get_last_message_text(self):
        messages = self.client.beta.threads.messages.list(
            thread_id=self.id,
            limit=1
        )

        if len(messages.data) == 0 or len(messages.data[0].content) == 0:
            return ""

        return messages.data[0].content[0].text.value

    def _get_last_assistant_message(self):
        messages = self.client.beta.threads.messages.list(
            thread_id=self.id,
            limit=1
        )

        if len(messages.data) == 0 or len(messages.data[0].content) == 0:
            raise Exception("No messages found in the thread")

        message = messages.data[0]

        if message.role == "assistant":
            return message

        raise Exception("No assistant message found in the thread")

    def execute_tool(self, tool_call, recipient_agent=None, event_handler=None, tool_names=[]):
        if not recipient_agent:
            recipient_agent = self.recipient_agent

        funcs = recipient_agent.functions
        func = next((func for func in funcs if func.__name__ == tool_call.function.name), None)

        if not func:
            return f"Error: Function {tool_call.function.name} not found. Available functions: {[func.__name__ for func in funcs]}"

        try:
            # init tool
            args = tool_call.function.arguments
            args = json.loads(args) if args else {}
            func = func(**args)
            for tool_name in tool_names:
                if tool_name == tool_call.function.name and (
                        hasattr(func, "one_call_at_a_time") and func.one_call_at_a_time):
                    return f"Error: Function {tool_call.function.name} is already called. You can only call this function once at a time. Please wait for the previous call to finish before calling it again."
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
