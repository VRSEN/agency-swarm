import asyncio
import inspect
import time
from typing import Literal, Awaitable, Callable, Any, Coroutine, Tuple
import openai
from openai.types.beta.threads import RequiredActionFunctionToolCall

from agency_swarm.agents import Agent
from agency_swarm.agents.async_agent import AsyncAgent
from agency_swarm.messages import MessageOutput
from agency_swarm.user import User
from agency_swarm.util.async_oai import get_openai_client


async def to_async(func: Callable[[], Any]) -> Any:
    return func()


import itertools
from typing import TypeVar, Callable, Awaitable

from typing import TypeVar, Callable, Awaitable

# Define a type variable T for the output of g and input of f
T = TypeVar('T')
# Define a type variable R for the output of f
R = TypeVar('R')


def compose_async_funcs(f: Callable[[T], Awaitable[R]], g: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[R]]:
    async def composed_function(*args, **kwargs) -> R:
        result_of_g = await g(*args, **kwargs)
        return await f(result_of_g)

    return composed_function


async def do_this_then_that(this: Awaitable[Any], that: Awaitable[T]) -> Awaitable[T]:
    await this
    return await that


class AsyncThread:
    id: str
    thread = None
    run = None

    def __init__(self, agent: Literal[AsyncAgent, User], recipient_agent: AsyncAgent):
        self.agent = agent
        self.recipient_agent: AsyncAgent = recipient_agent
        self.client: openai.AsyncOpenAI = get_openai_client()

    async def get_completion(self, message: str, yield_messages=True) -> list[MessageOutput]:
        result: list[MessageOutput] = []
        if not self.thread:
            self.thread = await self.client.beta.threads.create()
            self.id = self.thread.id

        # send message
        await self.client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=message
        )

        result.extend([MessageOutput("text", self.agent.name, self.recipient_agent.name, message)])

        # create run
        self.run = await self.client.beta.threads.runs.create(
            thread_id=self.thread.id,
            assistant_id=self.recipient_agent.id,
        )

        while self.run.status in ['queued', 'in_progress']:
            # wait until run completes
            await asyncio.wait_for(self.wait_for_status_change(), timeout=120)

            # function execution
            if self.run.status == "requires_action":
                tool_outputs, message_outputs = await self.process_requires_action()  #

                print(f"\n\n ********\nasync_thread.py/get_completion \n\ttool_outputs: {tool_outputs}\n\t message_outputs: {[msg.content for msg in message_outputs]} ")

                self.run = await self.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=self.thread.id,
                    run_id=self.run.id,
                    tool_outputs=list(tool_outputs)
                )
                result.extend(message_outputs)
            # error
            elif self.run.status == "failed":
                raise Exception("Run Failed. Error: ", self.run.last_error)
            # return assistant message
            else:
                messages = await self.client.beta.threads.messages.list(
                    thread_id=self.id
                )
                result.extend([MessageOutput("text", self.recipient_agent.name, self.agent.name,
                                             messages.data[0].content[0].text.value)])

        return result

    async def process_requires_action(self) -> Tuple[list[dict], list[MessageOutput]]:
        tool_calls: list[RequiredActionFunctionToolCall] = self.run.required_action.submit_tool_outputs.tool_calls
        data: list[Tuple[dict[str, str], MessageOutput, list[MessageOutput]]] = [({"tool_call_id": tool_call.id},
                                                                                  MessageOutput("function",
                                                                                                self.recipient_agent.name,
                                                                                                self.agent.name,
                                                                                                str(tool_call.function)),
                                                                                  await self.get_function_output(
                                                                                      tool_call)
                                                                                  ) for tool_call in tool_calls]

        tool_outputs: list[dict[str, str]] = [{**tool_data, "output": str(item.content)} for
                                              tool_data, function_call, function_output in data for item in
                                              function_output]
        # [item for sublist in original_list for item in (sublist if isinstance(sublist, list) else [sublist])]
        message_outputs: list[MessageOutput] = [item for _, function_call, function_output in data for item in
                                                [function_call, *function_output]]

        # message_outputs: list[MessageOutput] = [item for h,t in _message_outputs for item in [h,*t]]

        # submit tool outputs
        return tool_outputs, message_outputs

    async def get_function_output(self, tool_call) -> list[MessageOutput]:
        output = await self._execute_tool(tool_call)
        if inspect.isgenerator(output):
            return [item for item in output if isinstance(item, MessageOutput)]
        else:
            return [MessageOutput("function_output",
                                  tool_call.function.name,
                                  self.recipient_agent.name,
                                  output)]

    async def wait_for_status_change(self):
        while self.run.status in ['queued', 'in_progress']:
            await asyncio.sleep(5)
            self.run = await self.client.beta.threads.runs.retrieve(
                thread_id=self.thread.id,
                run_id=self.run.id
            )

    def ensure_awaitable(self, func):
        async def async_func():
            return func()
        return async_func
    async def _execute_tool(self, tool_call):
        funcs = self.recipient_agent.functions
        func_calls = [func for func in funcs if func.__name__ == tool_call.function.name]
        func_calls_with_args  = [func(**eval(tool_call.function.arguments)) for func in func_calls]
        async_calls = [func.run() if asyncio.iscoroutinefunction(func.run) else self.ensure_awaitable(func.run)() for func in func_calls_with_args]
        done, pending = await asyncio.wait(async_calls, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        return list(done)[0].result()
