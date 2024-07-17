import asyncio
import inspect
import json
import os
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

from concurrent.futures import ThreadPoolExecutor, as_completed

class Thread:
    async_mode: str = None
    max_workers: int = 4

    @property
    def thread_url(self):
        return f'https://platform.openai.com/playground/assistants?assistant={self.recipient_agent.assistant.id}&mode=assistant&thread={self.id}'

    def __init__(self, agent: Union[Agent, User], recipient_agent: Agent):
        self.agent = agent
        self.recipient_agent = recipient_agent

        self.client = get_openai_client()

        self.id = None
        self.thread = None
        self.run = None
        self.stream = None

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
        print(f'THREAD:[ {sender_name} -> {recipient_agent.name} ]: URL {self.thread_url}')

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
                tool_outputs_and_names = [] # list of tuples (name, tool_output)
                sync_tool_calls = [tool_call for tool_call in tool_calls if tool_call.function.name == "SendMessage"]
                async_tool_calls = [tool_call for tool_call in tool_calls if tool_call.function.name != "SendMessage"]

                def handle_output(tool_call, output):
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
                            yield MessageOutput("function_output", tool_call.function.name, recipient_agent.name, output, tool_call)

                    for tool_output in tool_outputs_and_names:
                        if tool_output[1]["tool_call_id"] == tool_call.id:
                            tool_output[1]["output"] = output

                if len(async_tool_calls) > 0 and self.async_mode == "tools_threading":
                    max_workers = min(self.max_workers, os.cpu_count() or 1)  # Use at most 4 workers or the number of CPUs available
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {}
                        for tool_call in async_tool_calls:
                            if yield_messages:
                                yield MessageOutput("function", recipient_agent.name, self.agent.name, str(tool_call.function), tool_call)
                            futures[executor.submit(self.execute_tool, tool_call, recipient_agent, event_handler, tool_outputs_and_names)] = tool_call
                            tool_outputs_and_names.append((tool_call.function.name, {"tool_call_id": tool_call.id}))

                        for future in as_completed(futures):
                            tool_call = futures[future]
                            output = future.result()
                            yield from handle_output(tool_call, output)
                else:
                    sync_tool_calls += async_tool_calls

                # execute sync tool calls
                for tool_call in sync_tool_calls:
                    if yield_messages:
                        yield MessageOutput("function", recipient_agent.name, self.agent.name, str(tool_call.function), tool_call)
                    output = self.execute_tool(tool_call, recipient_agent, event_handler, tool_outputs_and_names)
                    tool_outputs_and_names.append((tool_call.function.name, {"tool_call_id": tool_call.id, "output": output}))
                    yield from handle_output(tool_call, output)
                
                # split names and outputs
                tool_outputs = [tool_output for _, tool_output in tool_outputs_and_names]
                tool_names = [name for name, _ in tool_outputs_and_names]

                # await coroutines
                tool_outputs = self._execute_async_tool_calls_outputs(tool_outputs)

                # convert all tool outputs to strings
                for tool_output in tool_outputs:
                    if not isinstance(tool_output["output"], str):
                        tool_output["output"] = str(tool_output["output"])

                # send message tools can change this in other threads
                if event_handler:
                    event_handler.set_agent(self.agent)
                    event_handler.set_recipient_agent(recipient_agent)
                    
                # submit tool outputs
                try:
                    self._submit_tool_outputs(tool_outputs, event_handler)
                except BadRequestError as e:
                    if 'Runs in status "expired"' in e.message:
                        self.client.beta.threads.messages.create(
                            thread_id=self.thread.id,
                            role="user",
                            content="Previous request timed out. Please repeat the exact same tool calls in the exact same order with the same arguments."
                        )

                        self._create_run(recipient_agent, additional_instructions, event_handler, 'required', temperature=0)
                        self._run_until_done()

                        if self.run.status != "requires_action":
                            raise Exception("Run Failed. Error: ", self.run.last_error or self.run.incomplete_details)

                        # change tool call ids
                        tool_calls = self.run.required_action.submit_tool_outputs.tool_calls

                        if len(tool_calls) != len(tool_outputs):
                            tool_outputs = []
                            for i, tool_call in enumerate(tool_calls):
                                tool_outputs.append({"tool_call_id": tool_call.id, "output": "Error: openai run timed out. You can try again one more time."})
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
                elif 1 <= error_attempts < 5 and "something went wrong" in self.run.last_error.message.lower():
                    self.client.beta.threads.messages.create(
                        thread_id=self.thread.id,
                        role="user",
                        content="Continue."
                    )
                    self._create_run(recipient_agent, additional_instructions, event_handler, tool_choice)
                    error_attempts += 1
                else:
                    raise Exception("OpenAI Run Failed. Error: ", self.run.last_error.message)
            elif self.run.status == "incomplete":
                raise Exception("OpenAI Run Incomplete. Error: ", self.run.incomplete_details)
            # return assistant message
            else:
                message_obj = self._get_last_assistant_message()
                last_message = message_obj.content[0].text.value
                full_message += last_message

                if yield_messages:
                    yield MessageOutput("text", recipient_agent.name, self.agent.name, last_message, message_obj)

                if recipient_agent.response_validator:
                    try:
                        if isinstance(recipient_agent, Agent):
                            # TODO: allow users to modify the last message from response validator and replace it on OpenAI
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

                return last_message

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
                    temperature=temperature,
                    extra_body={"parallel_tool_calls": recipient_agent.parallel_tool_calls},
            ) as stream:
                stream.until_done()
                self.run = stream.get_final_run()
        else:
            self.run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=recipient_agent.id,
                additional_instructions=additional_instructions,
                tool_choice=tool_choice,
                max_prompt_tokens=recipient_agent.max_prompt_tokens,
                max_completion_tokens=recipient_agent.max_completion_tokens,
                truncation_strategy=recipient_agent.truncation_strategy,
                temperature=temperature,
                parallel_tool_calls=recipient_agent.parallel_tool_calls
            )
            self.run = self.client.beta.threads.runs.poll(
                thread_id=self.thread.id,
                run_id=self.run.id,
                # poll_interval_ms=500,
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

    def execute_tool(self, tool_call, recipient_agent=None, event_handler=None, tool_outputs_and_names={}):
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
            for tool_name in [name for name, _ in tool_outputs_and_names]:
                if tool_name == tool_call.function.name and (
                        hasattr(func, "one_call_at_a_time") and func.one_call_at_a_time):
                    return f"Error: Function {tool_call.function.name} is already called. You can only call this function once at a time. Please wait for the previous call to finish before calling it again."
            
            func.caller_agent = recipient_agent
            func.event_handler = event_handler

            return func.run()
        except Exception as e:
            error_message = f"Error: {e}"
            if "For further information visit" in error_message:
                error_message = error_message.split("For further information visit")[0]
            return error_message
        
    def _execute_async_tool_calls_outputs(self, tool_outputs):
        async_tool_calls = []
        for tool_output in tool_outputs:
            if inspect.iscoroutine(tool_output["output"]):
                async_tool_calls.append(tool_output)

        if async_tool_calls:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop = asyncio.get_event_loop()

            results = loop.run_until_complete(asyncio.gather(*[call["output"] for call in async_tool_calls]))
            
            for tool_output, result in zip(async_tool_calls, results):
                tool_output["output"] = str(result)
        
        return tool_outputs










