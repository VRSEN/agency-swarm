from typing import TYPE_CHECKING, Any, Dict, Generic, TypeVar, Union

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from langchain.schema import AgentAction as LangchainAgentAction
    from langchain.schema import AgentFinish as LangchainAgentFinish
    from langchain.schema import HumanMessage as LangchainHumanMessage


# Create base classes that match langchain's structure
class BaseAgentAction(BaseModel):
    tool: str
    tool_input: Union[str, Dict[str, Any]] = Field(default_factory=dict)
    log: str = ""


class BaseAgentFinish(BaseModel):
    return_values: Dict[str, Any] = Field(default_factory=dict)
    log: str = ""


class BaseHumanMessage(BaseModel):
    content: str = ""


T = TypeVar("T")


class Proxy(Generic[T]):
    def __init__(self, default_impl: T):
        self._impl: T = default_impl

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._impl(*args, **kwargs)

    def set_implementation(self, impl: T) -> None:
        self._impl = impl


# Initialize with our base implementations
AgentAction = Proxy[Union[BaseAgentAction, "LangchainAgentAction"]](BaseAgentAction)
AgentFinish = Proxy[Union[BaseAgentFinish, "LangchainAgentFinish"]](BaseAgentFinish)
HumanMessage = Proxy[Union[BaseHumanMessage, "LangchainHumanMessage"]](BaseHumanMessage)


def use_langchain_types() -> None:
    """Switch to using langchain types after langchain is imported"""
    global AgentAction, AgentFinish, HumanMessage
    from langchain.schema import AgentAction as LangchainAgentAction
    from langchain.schema import AgentFinish as LangchainAgentFinish
    from langchain.schema import HumanMessage as LangchainHumanMessage

    AgentAction.set_implementation(LangchainAgentAction)
    AgentFinish.set_implementation(LangchainAgentFinish)
    HumanMessage.set_implementation(LangchainHumanMessage)
