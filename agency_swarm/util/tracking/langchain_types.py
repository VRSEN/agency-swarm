from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from langchain.schema import AgentAction as LangchainAgentAction
    from langchain.schema import AgentFinish as LangchainAgentFinish
    from langchain.schema import HumanMessage as LangchainHumanMessage

# Define TypeVars that can be either our placeholder or langchain types
AgentAction = TypeVar("AgentAction", bound="LangchainAgentAction")
AgentFinish = TypeVar("AgentFinish", bound="LangchainAgentFinish")
HumanMessage = TypeVar("HumanMessage", bound="LangchainHumanMessage")


def use_langchain_types():
    """Switch to using langchain types after langchain is imported"""
    global AgentAction, AgentFinish, HumanMessage
    from langchain.schema import AgentAction as LangchainAgentAction
    from langchain.schema import AgentFinish as LangchainAgentFinish
    from langchain.schema import HumanMessage as LangchainHumanMessage

    AgentAction = LangchainAgentAction
    AgentFinish = LangchainAgentFinish
    HumanMessage = LangchainHumanMessage
