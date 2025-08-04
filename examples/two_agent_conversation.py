"""
Two-Agent Conversation Demo

The simplest example of two agents working together.
Manager delegates research tasks to Researcher who uses web search tools.
"""

import asyncio
import os
import sys

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agents import function_tool
from dotenv import load_dotenv

from agency_swarm import Agency, Agent

load_dotenv(override=True)


# Tools following OpenAI SDK patterns
@function_tool
def search_web(query: str) -> str:
    """
    Search the web for information.

    Args:
        query: The search query

    Returns:
        Search results as a string
    """
    # Mock search results for demo
    if "python" in query.lower():
        return "Python is a programming language. Latest version: 3.12"
    elif "weather" in query.lower():
        return "Current weather: 72°F, partly cloudy"
    else:
        return f"Found information about: {query}"


@function_tool
def summarize_text(text: str, max_length: int = 100) -> str:
    """
    Summarize text to a specified length.

    Args:
        text: The text to summarize
        max_length: Maximum length of summary in characters

    Returns:
        Summarized text
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


# Create agents
manager = Agent(
    name="Manager",
    instructions="You're a manager. When asked questions, delegate to the Researcher and return their exact response.",
)

researcher = Agent(
    name="Researcher",
    instructions="You're a researcher. When asked about a topic, use search_web to find information and return EXACTLY what the tool returns. Don't add extra information.",
    tools=[search_web, summarize_text],
)

# Create agency
agency = Agency(
    manager,
    communication_flows=[(manager, researcher)],
)


async def run_demo():
    """Demonstrates simple agent collaboration."""
    print("\n🔍 Two-Agent Research Demo")
    print("Manager delegates research to Researcher\n")

    # Example query
    response = await agency.get_response("What can you tell me about Python programming?")
    print(f"Answer: {response.final_output}")

    print("\n💡 Notice: The Researcher used the search_web tool!")
    print("   The simple response came from our mock function.")


if __name__ == "__main__":
    asyncio.run(run_demo())
