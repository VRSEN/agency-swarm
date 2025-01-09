from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal, Union

from docstring_parser import parse
from pydantic import BaseModel
from openai.types.beta.threads import Message, TextContentBlock, Text

from agency_swarm.util.shared_state import SharedState


class BaseTool(BaseModel, ABC):
    _shared_state: ClassVar[SharedState] = None
    _caller_agent: Any = None
    _event_handler: Any = None
    _tool_call: Any = None

    def __init__(self, caller_tool = None, **kwargs):
        if not self.__class__._shared_state:
            self.__class__._shared_state = SharedState()
        super().__init__(**kwargs)

        # initialize BaseTool if it's called by another BaseTool
        if caller_tool:
            assert isinstance(caller_tool, BaseTool)
            self._caller_agent = caller_tool._caller_agent
            self._event_handler = caller_tool._event_handler
            self._tool_call = caller_tool._tool_call

        # Ensure all ToolConfig variables are initialized
        config_defaults = {
            "strict": False,
            "one_call_at_a_time": False,
            "output_as_result": False,
            "async_mode": None,
        }

        for key, value in config_defaults.items():
            if not hasattr(self.ToolConfig, key):
                setattr(self.ToolConfig, key, value)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # every derived class of BaseTool automatically uses its class name as name
        cls.name = cls.__name__

    class ToolConfig:
        strict: bool = False
        one_call_at_a_time: bool = False
        # return the tool output as assistant message
        output_as_result: bool = False
        async_mode: Union[Literal["threading"], None] = None

    @classmethod
    @property
    def openai_schema(cls):
        """
        Return the schema in the format of OpenAI's schema as jsonschema

        Note:
            Its important to add a docstring to describe how to best use this class, it will be included in the description attribute and be part of the prompt.

        Returns:
            model_json_schema (dict): A dictionary in the format of OpenAI's schema as jsonschema
        """
        schema = cls.model_json_schema()
        docstring = parse(cls.__doc__ or "")
        parameters = {
            k: v for k, v in schema.items() if k not in ("title", "description")
        }
        for param in docstring.params:
            if (name := param.arg_name) in parameters["properties"] and (
                description := param.description
            ):
                if "description" not in parameters["properties"][name]:
                    parameters["properties"][name]["description"] = description

        parameters["required"] = sorted(
            k for k, v in parameters["properties"].items() if "default" not in v
        )

        if "description" not in schema:
            if docstring.short_description:
                schema["description"] = docstring.short_description
            else:
                schema["description"] = (
                    f"Correctly extracted `{cls.__name__}` with all "
                    f"the required parameters with correct types"
                )

        schema = {
            "name": schema["title"],
            "description": schema["description"],
            "parameters": parameters,
        }

        strict = getattr(cls.ToolConfig, "strict", False)
        if strict:
            schema["strict"] = True
            schema["parameters"]["additionalProperties"] = False
            # iterate through defs and set additionalProperties to false
            if "$defs" in schema["parameters"]:
                for def_ in schema["parameters"]["$defs"].values():
                    def_["additionalProperties"] = False

        return schema

    def get_agent_by_name(self, name: str):
        """
        Retrieve an agent by name from the agency.

        Parameters:
            name (str): The name of the agent to retrieve.

        Returns:
            Agent: The agent with the specified name.
        """
        if self._caller_agent is None:
            raise Exception("_caller_agent is not set.")
        if not hasattr(self._caller_agent, 'agency') or self._caller_agent.agency is None:
            raise Exception("_caller_agent does not have access to its agency")
        for agent in self._caller_agent.agency.agents:
            if agent.name == name:
                return agent
        raise ValueError(f"Agent with name '{name}' not found")

    def send_message_to_agent(self, recipient_agent_name: str, message: str, **kwargs) -> str:
        """
        Initiate a thread to another agent, then send a message and return the response.

        Parameters:
            recipient_agent_name (str): The name of the agent to send the message to.
            message (str): The message to send.
            **kwargs: Additional arguments to be passed to the Thread's `get_completion` method.

        Returns:
            str: The response from the recipient agent.
        """

        # initiate a thread to recipient
        recipient_agent = self.get_agent_by_name(recipient_agent_name)
        from agency_swarm.threads.thread import Thread  # Import here to avoid circular imports
        thread = Thread(agent=self, recipient_agent=recipient_agent)

        # print the message from tool
        event_handler = self._event_handler
        event_handler.set_agent(self)
        event_handler.set_recipient_agent(recipient_agent)

        event_handler_instance = event_handler()
        content = TextContentBlock(text=Text(annotations=[], value=message), type="text")
        fake_oai_message = Message(
            id="fake-id",
            content = [content],
            created_at=0,
            object="thread.message",
            role="user",
            status="completed",
            thread_id="fake-id"
        )
        event_handler_instance.on_message_created(fake_oai_message)

        # send the message
        res = thread.get_completion(
            message=message,
            recipient_agent=recipient_agent,
            event_handler=self._event_handler,
            **kwargs
        )

        # generate next message until getting the response
        while True:
            try:
                message = next(res)
            except StopIteration as e:
                return e.value

    @abstractmethod
    def run(self):
        pass
