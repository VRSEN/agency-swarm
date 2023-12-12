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
                t: Tuple[list[dict], list[(MessageOutput,MessageOutput)]] = await self.process_requires_action()  #
                tool_outputs = t[0]
                message_outputs = [function_output_message_output for function_call_message_output, function_output_message_output in t[1]]

                self.run = await self.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=self.thread.id,
                    run_id=self.run.id,
                    tool_outputs=tool_outputs
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

    async def process_requires_action(self) -> Tuple[list[dict], list[(MessageOutput,MessageOutput)]]:
        tool_calls: list[RequiredActionFunctionToolCall] = self.run.required_action.submit_tool_outputs.tool_calls
        data: list[Tuple[dict[str,str],MessageOutput, MessageOutput]]= [({"tool_call_id": tool_call.id},
                 MessageOutput("function", self.recipient_agent.name, self.agent.name, str(tool_call.function)),
                 MessageOutput("function_output", tool_call.function.name,
                               self.recipient_agent.name, await self._execute_tool(tool_call))
                 ) for tool_call in tool_calls]

        tool_outputs: list[dict] = [{**tool_data, "output": str(function_output.content)} for
                                    tool_data, function_call, function_output in data]

        message_outputs: list[(MessageOutput, MessageOutput)] = [(function_call, function_output) for _, function_call, function_output in data]

        # submit tool outputs
        return tool_outputs, message_outputs

    async def wait_for_status_change(self):
        while self.run.status in ['queued', 'in_progress']:
            await asyncio.sleep(5)
            self.run = await self.client.beta.threads.runs.retrieve(
                thread_id=self.thread.id,
                run_id=self.run.id
            )

    async def _execute_tool(self, tool_call):
        funcs = self.recipient_agent.functions
        func = next(iter([func for func in funcs if func.__name__ == tool_call.function.name]))
        try:
            # init tool
            func = func(**eval(tool_call.function.arguments))
            # get outputs from the tool
            output = await func.run()

            return output
        except Exception as e:
            return "Error: " + str(e)
